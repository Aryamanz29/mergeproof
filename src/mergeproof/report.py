"""Results of evaluating a policy against a context."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
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


class Annotation(BaseModel):
    """A message pinned to a file, for the Checks tab and the diff view."""

    path: str
    message: str
    line: int = 1


class Outcome(BaseModel):
    status: Status
    summary: str
    details: list[str] = Field(default_factory=list)
    fix: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    annotations: list[Annotation] = Field(default_factory=list)


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
    base_ref: str | None = None
    policy_path: str = "mergeproof.yaml"
    evaluated_at: str = Field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"))
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

    def counts(self) -> dict[Status, int]:
        counts = dict.fromkeys(Status, 0)
        for _, req in self.requirements:
            counts[req.outcome.status] += 1
        return counts

    def headline(self) -> str:
        """`3 of 5 requirements satisfied, 2 pending`; short enough for a commit status."""
        total = len(self.requirements)
        if total == 0:
            return "no rules apply to this change"
        counts = self.counts()
        satisfied = counts[Status.PASS] + counts[Status.SKIP]
        rest = ", ".join(f"{n} {status.value}" for status, n in counts.items() if n and status in UNMET)
        return f"{satisfied} of {total} requirements satisfied" + (f", {rest}" if rest else "")

    def annotations(self) -> list[Annotation]:
        return [a for _, req in self.requirements for a in req.outcome.annotations]

    def evidence_template(self) -> dict[str, Any]:
        return evidence.merge_templates([req.evidence_template for _, req in self.unmet()])

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> Report:
        return cls.model_validate_json(text)
