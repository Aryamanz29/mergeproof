"""Results of evaluating a policy against a context."""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field

from mergeproof import evidence
from mergeproof.policy import Severity


class Status(enum.StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    PENDING = "pending"
    SKIP = "skip"
    ERROR = "error"


UNMET = frozenset({Status.FAIL, Status.WARN, Status.PENDING, Status.ERROR})

EXIT_CODES = {Status.PASS: 0, Status.WARN: 0, Status.FAIL: 1, Status.PENDING: 2}
EXIT_USAGE = 3


class Outcome(BaseModel):
    status: Status
    summary: str
    details: list[str] = Field(default_factory=list)
    fix: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class RequirementResult(BaseModel):
    label: str
    check: str
    severity: Severity
    outcome: Outcome
    instructions: str | None = None
    evidence_template: dict[str, Any] = Field(default_factory=dict)


class RuleResult(BaseModel):
    id: str
    description: str = ""
    severity: Severity
    matched: bool
    files: list[str] = Field(default_factory=list)
    instructions: str | None = None
    requirements: list[RequirementResult] = Field(default_factory=list)


class Report(BaseModel):
    project: str | None = None
    evidence_block: str = "evidence"
    source: str = "local"
    repo: str | None = None
    number: int | None = None
    head_sha: str | None = None
    rules: list[RuleResult] = Field(default_factory=list)

    @property
    def matched(self) -> list[RuleResult]:
        return [r for r in self.rules if r.matched]

    @property
    def requirements(self) -> list[tuple[RuleResult, RequirementResult]]:
        return [(rule, req) for rule in self.matched for req in rule.requirements]

    @property
    def verdict(self) -> Status:
        blocking = [req for _, req in self.requirements if req.severity == Severity.BLOCK]
        if any(req.outcome.status in (Status.FAIL, Status.ERROR) for req in blocking):
            return Status.FAIL
        if any(req.outcome.status == Status.PENDING for req in blocking):
            return Status.PENDING
        if any(req.outcome.status in UNMET for _, req in self.requirements):
            return Status.WARN
        return Status.PASS

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.verdict]

    def unmet(self) -> list[tuple[RuleResult, RequirementResult]]:
        return [(rule, req) for rule, req in self.requirements if req.outcome.status in UNMET]

    def evidence_template(self) -> dict[str, Any]:
        return evidence.merge_templates([req.evidence_template for _, req in self.unmet()])

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> Report:
        return cls.model_validate_json(text)
