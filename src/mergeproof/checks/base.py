"""Base class for checks.

A check answers one question about a pull request. It declares its
parameters as a pydantic model, runs against a :class:`Context`, and returns
an :class:`Outcome`. Third-party checks register under the
``mergeproof.checks`` entry-point group.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from mergeproof.context import Context
from mergeproof.report import Outcome, Status


class Check(ABC):
    id: ClassVar[str]
    description: ClassVar[str] = ""
    needs_github: ClassVar[bool] = False

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

    def parse_params(self, raw: dict[str, Any]) -> BaseModel:
        return self.Params(**raw)

    @abstractmethod
    def run(self, ctx: Context, params: Any, files: list[str]) -> Outcome:
        """*files* are the changed paths that made the enclosing rule apply."""

    def explain(self, params: Any) -> str:
        """One sentence a contributor or agent can act on."""
        return self.description

    def evidence_template(self, params: Any) -> dict[str, Any]:
        """Keys this check expects in the evidence block, with placeholder values."""
        return {}


def ok(summary: str, **kw: Any) -> Outcome:
    return Outcome(status=Status.PASS, summary=summary, **kw)


def fail(summary: str, fix: str | None = None, **kw: Any) -> Outcome:
    return Outcome(status=Status.FAIL, summary=summary, fix=fix, **kw)


def warn(summary: str, fix: str | None = None, **kw: Any) -> Outcome:
    return Outcome(status=Status.WARN, summary=summary, fix=fix, **kw)


def pending(summary: str, fix: str | None = None, **kw: Any) -> Outcome:
    return Outcome(status=Status.PENDING, summary=summary, fix=fix, **kw)


def skip(summary: str, **kw: Any) -> Outcome:
    return Outcome(status=Status.SKIP, summary=summary, **kw)


def error(summary: str, **kw: Any) -> Outcome:
    return Outcome(status=Status.ERROR, summary=summary, **kw)
