"""evidence.traces - before/after observability traces (Braintrust by default).

Each item in the evidence list is a pair proving the behaviour change on a live system::

    traces:
      - tool: query_assets
        before: https://www.braintrust.dev/app/<org>/p/<project>/logs?r=<id>
        after:  https://www.braintrust.dev/app/<org>/p/<project>/logs?r=<id>

With ``verify: true`` and ``BRAINTRUST_API_KEY`` set, each id is looked up through BTQL so a
pasted-but-nonexistent link cannot satisfy the gate.
"""

from __future__ import annotations

import os
import re
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..context import PRContext
from ..models import CheckResult
from .base import Check, errored, failed, passed

BRAINTRUST_URL = (
    r"^https://www\.braintrust\.dev/app/(?P<org>[^/]+)/p/(?P<project>[^/?]+)/logs\?"
    r"(?:.*&)?r=(?P<id>[0-9a-fA-F-]+)"
)


class TraceVerifier(Protocol):
    def exists(self, project: str, trace_id: str) -> bool: ...


class BraintrustVerifier:
    def __init__(self, api_key: str, api_url: str = "https://api.braintrust.dev", timeout: float = 30.0):
        self._client = httpx.Client(base_url=api_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)

    def exists(self, project: str, trace_id: str) -> bool:
        safe_project = project.replace("'", "")
        safe_id = re.sub(r"[^0-9a-fA-F-]", "", trace_id)
        query = (
            f"SELECT id FROM project_logs('{safe_project}') "
            f"WHERE id = '{safe_id}' OR root_span_id = '{safe_id}' LIMIT 1"
        )
        r = self._client.post("/btql", json={"query": query, "fmt": "json"})
        r.raise_for_status()
        return bool(r.json().get("data"))


class EvidenceTraces(Check):
    id = "evidence.traces"
    description = (
        "The evidence block lists before/after trace links proving the change on a live system. "
        "Each pair must be two distinct trace ids from the expected project."
    )

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        key: str = "traces"
        min_pairs: int = 1
        project: str | None = Field(default=None, description="Trace project the links must point to")
        url_pattern: str = Field(default=BRAINTRUST_URL, description="Regex with `project` and `id` groups")
        require_before: bool = True
        verify: bool = Field(default=False, description="Look the ids up via the Braintrust API")
        api_key_env: str = "BRAINTRUST_API_KEY"
        block: str = "evidence"

    verifier: TraceVerifier | None = None  # injectable for tests / other backends

    def run(self, ctx: PRContext, params: Params, files: list[str]) -> CheckResult:
        ev = ctx.evidence(params.block)
        if ev.errors:
            return failed("evidence block could not be parsed", details=ev.errors, fix=self._fix(params))
        items = ev.get(params.key)
        if not isinstance(items, list) or not items:
            return failed(f"no `{params.key}` list in evidence block", fix=self._fix(params))

        rx = re.compile(params.url_pattern)
        problems: list[str] = []
        pairs: list[dict[str, str]] = []
        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                problems.append(f"item {i}: expected a mapping with `before`/`after`")
                continue
            parsed: dict[str, str] = {}
            for side in ("before", "after"):
                url = item.get(side)
                if not url:
                    if side == "after" or params.require_before:
                        problems.append(f"item {i}: missing `{side}`")
                    continue
                m = rx.match(str(url))
                if not m:
                    problems.append(f"item {i}: `{side}` is not a recognised trace URL")
                    continue
                if params.project and m.group("project") != params.project:
                    problems.append(
                        f"item {i}: `{side}` points to project `{m.group('project')}`, expected `{params.project}`"
                    )
                    continue
                parsed[side] = m.group("id")
            if "before" in parsed and "after" in parsed and parsed["before"] == parsed["after"]:
                problems.append(f"item {i}: `before` and `after` are the same trace")
            if "after" in parsed and (not params.require_before or "before" in parsed):
                parsed["project"] = m.group("project")
                pairs.append(parsed)

        if problems:
            return failed(f"{len(problems)} problem(s) in `{params.key}`", details=problems, fix=self._fix(params))
        if len(pairs) < params.min_pairs:
            return failed(f"{len(pairs)} valid pair(s), need {params.min_pairs}", fix=self._fix(params))

        if params.verify:
            verifier = self.verifier
            if verifier is None:
                key = os.environ.get(params.api_key_env)
                if not key:
                    return errored(f"verify=true but {params.api_key_env} is not set")
                verifier = BraintrustVerifier(key)
            missing: list[str] = []
            try:
                for p in pairs:
                    for side in ("before", "after"):
                        if side in p and not verifier.exists(p["project"], p[side]):
                            missing.append(f"{side} trace `{p[side]}` not found in `{p['project']}`")
            except httpx.HTTPError as exc:
                return errored(f"trace verification failed: {type(exc).__name__}")
            if missing:
                return failed("trace link(s) do not resolve", details=missing, fix=self._fix(params))
            return passed(f"{len(pairs)} before/after pair(s), all verified", data={"pairs": pairs})
        return passed(f"{len(pairs)} before/after pair(s)", data={"pairs": pairs})

    def _fix(self, params: Params) -> str:
        return (
            f"Reproduce the issue on the live tenant, capture the trace (`before`), deploy the fix, "
            f"re-run the same call and capture the trace (`after`); put both links under "
            f"`{params.key}` in the evidence block. " + self.explain(params)
        )

    def explain(self, params: Params) -> str:
        proj = f" from project `{params.project}`" if params.project else ""
        v = " Ids are verified against the API." if params.verify else ""
        return (
            f"≥{params.min_pairs} `before`/`after` trace-link pair(s){proj} under `{params.key}` "
            f"in the evidence block.{v}"
        )

    def evidence_template(self, params: Params) -> dict[str, Any]:
        proj = params.project or "<project>"
        return {
            params.key: [
                {
                    "tool": "<what was exercised>",
                    "before": f"https://www.braintrust.dev/app/<org>/p/{proj}/logs?r=<trace-id>",
                    "after": f"https://www.braintrust.dev/app/<org>/p/{proj}/logs?r=<trace-id>",
                }
            ]
        }
