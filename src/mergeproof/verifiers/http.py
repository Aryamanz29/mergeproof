from __future__ import annotations

import os
import re

import httpx

from mergeproof.verifiers.base import Verification


class HttpVerifier:
    """A link is valid when it answers with a 2xx or 3xx status.

    ``auth_header_env`` names an environment variable whose value is sent as
    the ``Authorization`` header, so private dashboards can be checked without
    the token ever appearing in the policy.
    """

    def __init__(self, auth_header_env: str | None = None, timeout: float = 15.0, method: str = "HEAD") -> None:
        headers = {"User-Agent": "mergeproof"}
        if auth_header_env:
            token = os.environ.get(auth_header_env)
            if token:
                headers["Authorization"] = (
                    token if token.lower().startswith(("bearer ", "basic ")) else f"Bearer {token}"
                )
        self.method = method.upper()
        self._client = httpx.Client(headers=headers, timeout=timeout, follow_redirects=True)

    def verify(self, url: str, match: re.Match[str]) -> Verification:
        response = self._client.request(self.method, url)
        if response.status_code == 405 and self.method == "HEAD":
            response = self._client.get(url)
        length = response.headers.get("content-length")
        return Verification(
            found=response.status_code < 400,
            source="http",
            at=response.headers.get("last-modified"),
            size=f"{int(length):,} bytes" if length and length.isdigit() else None,
            url=str(response.url) if str(response.url) != url else None,
            facts={"status": response.status_code, "type": (response.headers.get("content-type") or "").split(";")[0]},
        )
