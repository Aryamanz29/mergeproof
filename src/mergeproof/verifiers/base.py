"""Verifiers resolve a link in the evidence block to an answer with provenance.

The core ships ``http`` (the URL answers 2xx). Anything vendor-specific,
such as looking a trace id up in an observability backend, lives in a
plugin registered under the ``mergeproof.verifiers`` entry-point group.

A verifier may return a plain bool or a :class:`Verification`. The second
says what was found, not only that it was: which object, when it was
recorded, how big it is. That is what a reviewer needs to tell a real
trace from an empty one without opening it, and what the receipt keeps.
"""

from __future__ import annotations

import re
from importlib.metadata import entry_points
from typing import Any, Protocol

from pydantic import BaseModel, Field

ENTRY_POINT_GROUP = "mergeproof.verifiers"


class Verification(BaseModel):
    found: bool
    source: str = Field(default="", description="Where it was looked up: http, langfuse, braintrust, ...")
    id: str | None = Field(default=None, description="The object's id at the source")
    at: str | None = Field(default=None, description="When the object was recorded, as the source reports it")
    size: str | None = Field(default=None, description="How big it is, in the source's own unit: `14 spans`")
    url: str | None = Field(default=None, description="Canonical URL when it differs from the pasted one")
    facts: dict[str, Any] = Field(default_factory=dict, description="Anything else worth keeping")

    def line(self) -> str:
        """One line for a comment or a receipt: `braintrust · mcp-internal · 14 spans · 2026-09-14T17:02Z`."""
        parts = [self.source, *(str(v) for v in self.facts.values() if v not in (None, "")), self.size, self.at]
        return " · ".join(p for p in parts if p) or ("found" if self.found else "not found")


class Verifier(Protocol):
    def __init__(self, **options: Any) -> None: ...

    def verify(self, url: str, match: re.Match[str]) -> bool | Verification:
        """Whether *url* exists, with provenance when the source can give it.

        *match* is the policy's pattern match, with named groups.
        """
        ...


def as_verification(result: bool | Verification, source: str) -> Verification:
    if isinstance(result, Verification):
        return result if result.source else result.model_copy(update={"source": source})
    return Verification(found=bool(result), source=source)


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
