"""Langfuse support for mergeproof.

Two extension points in one small package:

* ``LangfuseVerifier`` resolves a trace URL to the public API and reports whether the
  trace exists. Register it under ``mergeproof.verifiers`` and use ``verify: langfuse``.
* ``LangfuseTraces`` is ``evidence.links`` with Langfuse defaults, so a policy can say
  ``check: langfuse.traces`` and nothing else.
* ``LangfuseEval`` requires a dataset run named in the evidence block to score above thresholds:
  ``check: langfuse.eval`` with ``scorers: { correctness: 0.8 }``.
"""

from __future__ import annotations

import os
import re

import httpx
from pydantic import Field

from mergeproof.checks.eval_score import EvalRun, EvalScore, MissingCredentials
from mergeproof.checks.evidence_links import EvidenceLinks
from mergeproof.verifiers import Verification

TRACE_URL = r"^(?P<host>https?://[^/]+)/project/(?P<project>[^/]+)/traces/(?P<trace_id>[\w-]+)"


class LangfuseVerifier:
    """Look a trace up with ``GET {host}/api/public/traces/{trace_id}``.

    Credentials come from ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` (basic auth), the
    same variables the Langfuse SDKs read. ``host`` overrides the host taken from the link, for
    deployments where the UI and the API are served from different names.
    """

    def __init__(
        self,
        host: str | None = None,
        public_key_env: str = "LANGFUSE_PUBLIC_KEY",
        secret_key_env: str = "LANGFUSE_SECRET_KEY",
        timeout: float = 15.0,
    ) -> None:
        self.host = host.rstrip("/") if host else None
        public, secret = os.environ.get(public_key_env), os.environ.get(secret_key_env)
        auth = (public, secret) if public and secret else None
        self._client = httpx.Client(auth=auth, timeout=timeout, headers={"User-Agent": "mergeproof-langfuse"})

    def verify(self, url: str, match: re.Match[str]) -> Verification:
        groups = match.groupdict()
        host = self.host or groups.get("host")
        trace_id = groups.get("trace_id")
        if not host or not trace_id:
            raise ValueError("the link pattern must capture `host` and `trace_id`")
        response = self._client.get(f"{host}/api/public/traces/{trace_id}")
        if response.status_code == 404:
            return Verification(found=False, source="langfuse", id=trace_id)
        response.raise_for_status()
        trace = response.json() if response.content else {}
        observations = trace.get("observations")
        return Verification(
            found=True,
            source="langfuse",
            id=trace_id,
            at=trace.get("timestamp"),
            size=f"{len(observations)} observations" if isinstance(observations, list) else None,
            facts={"project": groups.get("project"), "name": trace.get("name")},
        )


class LangfuseTraces(EvidenceLinks):
    id = "langfuse.traces"
    description = "Before/after Langfuse trace links under `traces`, each verified against the Langfuse API."

    class Params(EvidenceLinks.Params):
        key: str = "traces"
        pattern: str = TRACE_URL
        verify: str | None = "langfuse"
        example: str = Field(default="https://langfuse.example.com/project/<project-id>/traces/<trace-id>")


RUN_URL = r"^(?P<host>https?://[^/]+)/.*?/datasets/(?P<dataset>[^/?#]+)/runs/(?P<run>[^/?#]+)"


class LangfuseEval(EvalScore):
    """Scores of a dataset run: the run's items from ``GET /api/public/datasets/{name}/runs/{run}``,
    each item's trace scores from ``GET /api/public/traces/{id}``, averaged per scorer.

    The reference is ``<dataset name>/<run name>`` or a link whose path ends in
    ``/datasets/<dataset>/runs/<run>``. Credentials are ``LANGFUSE_PUBLIC_KEY`` and
    ``LANGFUSE_SECRET_KEY``; the host comes from the link, ``host``, or ``LANGFUSE_HOST``.
    """

    id = "langfuse.eval"
    source = "langfuse"
    description = "A Langfuse dataset run named in the evidence block scores at least the thresholds given."

    class Params(EvalScore.Params):
        pattern: str | None = RUN_URL
        host: str | None = None
        public_key_env: str = "LANGFUSE_PUBLIC_KEY"
        secret_key_env: str = "LANGFUSE_SECRET_KEY"
        timeout: float = 15.0
        example: str = "<dataset name>/<run name>"

    def client(self, params: Params) -> httpx.Client:
        public, secret = os.environ.get(params.public_key_env), os.environ.get(params.secret_key_env)
        if not (public and secret):
            raise MissingCredentials(f"{params.public_key_env} and {params.secret_key_env} are not set")
        headers = {"User-Agent": "mergeproof-langfuse"}
        return httpx.Client(auth=(public, secret), timeout=params.timeout, headers=headers)

    def fetch_run(self, ref: str, match: re.Match[str] | None, params: Params) -> EvalRun:
        host = params.host or os.environ.get("LANGFUSE_HOST")
        if match:
            host = params.host or match.group("host")
            dataset, run = match.group("dataset"), match.group("run")
        elif "/" in ref:
            dataset, run = ref.split("/", 1)
        else:
            raise ValueError(f"`{ref}` should be <dataset name>/<run name> or a dataset run link")
        if not host:
            raise ValueError("no Langfuse host: give a link, set `host`, or export LANGFUSE_HOST")
        host = host.rstrip("/")
        client = self.client(params)
        response = client.get(f"{host}/api/public/datasets/{dataset}/runs/{run}")
        if response.status_code == 404:
            raise ValueError(f"no run {run!r} in dataset {dataset!r}")
        response.raise_for_status()
        body = response.json()
        items = body.get("datasetRunItems") or []
        totals: dict[str, list[float]] = {}
        for item in items:
            trace_id = item.get("traceId")
            if not trace_id:
                continue
            trace = client.get(f"{host}/api/public/traces/{trace_id}")
            if trace.status_code == 404:
                continue
            trace.raise_for_status()
            for score in trace.json().get("scores") or []:
                value = score.get("value")
                if isinstance(value, int | float) and score.get("name"):
                    totals.setdefault(str(score["name"]), []).append(float(value))
        scores = {name: sum(values) / len(values) for name, values in totals.items()}
        return EvalRun(
            id=str(body.get("id") or run),
            name=body.get("name") or run,
            at=body.get("createdAt"),
            count=len(items),
            scores=scores,
        )
