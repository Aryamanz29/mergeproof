"""Base class every check implements. Third parties subclass this and register via the
``mergeproof.checks`` entry-point group (see pyproject.toml)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from ..context import PRContext
from ..models import CheckResult, Status


class Check(ABC):
    id: ClassVar[str]
    description: ClassVar[str] = ""
    needs_github: ClassVar[bool] = False  # if True, reports PENDING in local mode

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

    def parse_params(self, raw: dict[str, Any]) -> BaseModel:
        return self.Params(**raw)

    @abstractmethod
    def run(self, ctx: PRContext, params: Any, files: list[str]) -> CheckResult:
        """``files`` are the changed paths that made the enclosing rule match."""

    def explain(self, params: Any) -> str:
        """One or two sentences telling a human or agent what satisfies this check."""
        return self.description

    def evidence_template(self, params: Any) -> dict[str, Any]:
        """Keys this check expects in the PR's evidence block, if any."""
        return {}


# Small constructors so checks read declaratively -------------------------------------


def passed(summary: str, **kw: Any) -> CheckResult:
    return CheckResult(status=Status.PASS, summary=summary, **kw)


def failed(summary: str, fix: str | None = None, **kw: Any) -> CheckResult:
    return CheckResult(status=Status.FAIL, summary=summary, fix=fix, **kw)


def pending(summary: str, fix: str | None = None, **kw: Any) -> CheckResult:
    return CheckResult(status=Status.PENDING, summary=summary, fix=fix, **kw)


def warned(summary: str, fix: str | None = None, **kw: Any) -> CheckResult:
    return CheckResult(status=Status.WARN, summary=summary, fix=fix, **kw)


def skipped(summary: str, **kw: Any) -> CheckResult:
    return CheckResult(status=Status.SKIP, summary=summary, **kw)


def errored(summary: str, **kw: Any) -> CheckResult:
    return CheckResult(status=Status.ERROR, summary=summary, **kw)
