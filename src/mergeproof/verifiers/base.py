"""Verifiers resolve a link in the evidence block to a yes/no answer.

The core ships ``http`` (the URL answers 2xx). Anything vendor-specific,
such as looking a trace id up in an observability backend, lives in a
plugin registered under the ``mergeproof.verifiers`` entry-point group.
"""

from __future__ import annotations

import re
from importlib.metadata import entry_points
from typing import Any, Protocol

ENTRY_POINT_GROUP = "mergeproof.verifiers"


class Verifier(Protocol):
    def __init__(self, **options: Any) -> None: ...

    def verify(self, url: str, match: re.Match[str]) -> bool:
        """Return True when *url* exists. *match* is the policy's pattern match, with named groups."""
        ...


class UnknownVerifier(LookupError):
    pass


def load_verifier(name: str, options: dict[str, Any] | None = None) -> Verifier:
    if name == "http":
        from mergeproof.verifiers.http import HttpVerifier

        return HttpVerifier(**(options or {}))
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.name == name:
            cls = ep.load()
            verifier: Verifier = cls(**(options or {}))
            return verifier
    raise UnknownVerifier(f"no verifier named {name!r}; install a plugin that provides it")
