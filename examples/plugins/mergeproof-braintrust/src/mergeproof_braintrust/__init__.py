"""Braintrust support for mergeproof.

* ``BraintrustVerifier`` looks a trace up through BTQL, so a pasted log link has to point at a
  row that exists in that project. Register under ``mergeproof.verifiers`` and use
  ``verify: braintrust``.
* ``BraintrustTraces`` is ``evidence.links`` with Braintrust defaults: ``check: braintrust.traces``.
* ``BraintrustEval`` requires an experiment named in the evidence block to score above thresholds:
  ``check: braintrust.eval`` with ``scorers: { Factuality: 0.85 }``.

Links look like ``https://www.braintrust.dev/app/<org>/p/<project>/logs?r=<id>``; the lookup
matches the id against ``id`` and ``root_span_id`` in ``project_logs('<project>')``.
"""

from __future__ import annotations

import os
import re

import httpx
from pydantic import Field

from mergeproof.checks.eval_score import EvalRun, EvalScore, MissingCredentials
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


EXPERIMENT_URL = (
    r"^https://www\.braintrust\.dev/app/(?P<org>[^/]+)/p/(?P<project>[^/?#]+)/experiments/(?P<experiment>[^/?#]+)"
)
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class BraintrustEval(EvalScore):
    """Scores of an experiment, from ``GET /v1/experiment/{id}/summarize``.

    The reference is an experiment id, an app link, or ``<project>/<experiment name>``.
    Needs ``BRAINTRUST_API_KEY``; without it the requirement stays pending.
    """

    id = "braintrust.eval"
    source = "braintrust"
    description = "A Braintrust experiment named in the evidence block scores at least the thresholds given."

    class Params(EvalScore.Params):
        pattern: str | None = EXPERIMENT_URL
        api_key_env: str = "BRAINTRUST_API_KEY"
        api_url: str = "https://api.braintrust.dev"
        project: str | None = Field(default=None, description="Project for references given by name")
        timeout: float = 30.0
        example: str = "https://www.braintrust.dev/app/<org>/p/<project>/experiments/<experiment>"

    def client(self, params: Params) -> httpx.Client:
        key = os.environ.get(params.api_key_env)
        if not key:
            raise MissingCredentials(f"{params.api_key_env} is not set")
        return httpx.Client(
            base_url=params.api_url,
            timeout=params.timeout,
            headers={"Authorization": f"Bearer {key}", "User-Agent": "mergeproof-braintrust"},
        )

    def fetch_run(self, ref: str, match: re.Match[str] | None, params: Params) -> EvalRun:
        project = params.project
        name_or_id = ref
        if match:
            project = match.group("project")
            name_or_id = match.group("experiment")
        elif "/" in ref and not UUID.match(ref):
            project, name_or_id = ref.split("/", 1)
        client = self.client(params)
        experiment_id = name_or_id
        if not UUID.match(name_or_id):
            if not project:
                raise ValueError(f"`{ref}` is an experiment name; give it as <project>/<name> or set `project`")
            found = client.get("/v1/experiment", params={"project_name": project, "experiment_name": name_or_id})
            found.raise_for_status()
            objects = found.json().get("objects") or []
            if not objects:
                raise ValueError(f"no experiment named {name_or_id!r} in project {project!r}")
            experiment_id = str(objects[0]["id"])
        experiment = client.get(f"/v1/experiment/{experiment_id}")
        experiment.raise_for_status()
        info = experiment.json()
        summary = client.get(f"/v1/experiment/{info['id']}/summarize", params={"summarize_scores": "true"})
        summary.raise_for_status()
        body = summary.json()
        scores = {
            name: float(entry["score"])
            for name, entry in (body.get("scores") or {}).items()
            if isinstance(entry, dict) and entry.get("score") is not None
        }
        metrics = body.get("metrics") or {}
        count = None
        for key in ("examples", "num_examples", "count"):
            value = metrics.get(key)
            if isinstance(value, dict) and value.get("metric") is not None:
                count = int(value["metric"])
                break
        return EvalRun(
            id=str(info["id"]),
            name=info.get("name"),
            at=info.get("created"),
            count=count,
            scores=scores,
            url=body.get("experiment_url"),
        )
