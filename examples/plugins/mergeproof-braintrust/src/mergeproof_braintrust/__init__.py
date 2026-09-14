"""Braintrust support for mergeproof.

* ``BraintrustVerifier`` looks a trace up through BTQL, so a pasted log link has to point at a
  row that exists in that project. Register under ``mergeproof.verifiers`` and use
  ``verify: braintrust``.
* ``BraintrustTraces`` is ``evidence.links`` with Braintrust defaults: ``check: braintrust.traces``.

Links look like ``https://www.braintrust.dev/app/<org>/p/<project>/logs?r=<id>``; the lookup
matches the id against ``id`` and ``root_span_id`` in ``project_logs('<project>')``.
"""

from __future__ import annotations

import os
import re

import httpx
from pydantic import Field

from mergeproof.checks.evidence_links import EvidenceLinks
from mergeproof.verifiers import Verification

TRACE_URL = r"^https://www\.braintrust\.dev/app/(?P<org>[^/]+)/p/(?P<project>[^/?]+)/logs\?(?:.*&)?r=(?P<trace_id>[0-9a-fA-F-]+)"


SPAN_LIMIT = 200


class BraintrustVerifier:
    """``POST /btql`` with a SQL query pinned to the trace id; needs ``BRAINTRUST_API_KEY``."""

    def __init__(
        self,
        api_key_env: str = "BRAINTRUST_API_KEY",
        api_url: str = "https://api.braintrust.dev",
        project: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        key = os.environ.get(api_key_env)
        if not key:
            raise ValueError(f"{api_key_env} is not set")
        self.project = project
        self._client = httpx.Client(
            base_url=api_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {key}", "User-Agent": "mergeproof-braintrust"},
        )

    def verify(self, url: str, match: re.Match[str]) -> Verification:
        groups = match.groupdict()
        project = self.project or groups.get("project")
        trace_id = groups.get("trace_id")
        if not project or not trace_id:
            raise ValueError("the link pattern must capture `project` and `trace_id`")
        safe_project = project.replace("'", "")
        safe_id = re.sub(r"[^0-9a-fA-F-]", "", trace_id)
        # Every span of the trace: the root (id = trace id) and its children (root_span_id = trace id).
        query = (
            f"SELECT id, created, span_attributes FROM project_logs('{safe_project}') "
            f"WHERE id = '{safe_id}' OR root_span_id = '{safe_id}' LIMIT {SPAN_LIMIT}"
        )
        response = self._client.post("/btql", json={"query": query, "fmt": "json"})
        response.raise_for_status()
        rows = response.json().get("data") or []
        if not rows:
            return Verification(found=False, source="braintrust", id=trace_id, facts={"project": project})
        root = next((r for r in rows if r.get("id") == safe_id), rows[0])
        created = [r["created"] for r in rows if r.get("created")]
        spans = f"{len(rows)}{'+' if len(rows) >= SPAN_LIMIT else ''} spans"
        return Verification(
            found=True,
            source="braintrust",
            id=trace_id,
            at=min(created) if created else None,
            size=spans,
            facts={"project": project, "name": (root.get("span_attributes") or {}).get("name")},
        )


class BraintrustTraces(EvidenceLinks):
    id = "braintrust.traces"
    description = "Before/after Braintrust log links under `traces`, each verified through BTQL."

    class Params(EvidenceLinks.Params):
        key: str = "traces"
        pattern: str = TRACE_URL
        verify: str | None = "braintrust"
        example: str = Field(default="https://www.braintrust.dev/app/<org>/p/<project>/logs?r=<trace-id>")
