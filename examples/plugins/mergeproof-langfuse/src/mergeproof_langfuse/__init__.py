"""Langfuse support for mergeproof.

Two extension points in one small package:

* ``LangfuseVerifier`` resolves a trace URL to the public API and reports whether the
  trace exists. Register it under ``mergeproof.verifiers`` and use ``verify: langfuse``.
* ``LangfuseTraces`` is ``evidence.links`` with Langfuse defaults, so a policy can say
  ``check: langfuse.traces`` and nothing else.
"""

from __future__ import annotations

import os
import re

import httpx
from pydantic import Field

from mergeproof.checks.evidence_links import EvidenceLinks

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

    def verify(self, url: str, match: re.Match[str]) -> bool:
        groups = match.groupdict()
        host = self.host or groups.get("host")
        trace_id = groups.get("trace_id")
        if not host or not trace_id:
            raise ValueError("the link pattern must capture `host` and `trace_id`")
        response = self._client.get(f"{host}/api/public/traces/{trace_id}")
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True


class LangfuseTraces(EvidenceLinks):
    id = "langfuse.traces"
    description = "Before/after Langfuse trace links under `traces`, each verified against the Langfuse API."

    class Params(EvidenceLinks.Params):
        key: str = "traces"
        pattern: str = TRACE_URL
        verify: str | None = "langfuse"
        example: str = Field(default="https://langfuse.example.com/project/<project-id>/traces/<trace-id>")
