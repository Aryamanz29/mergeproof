"""Policy and report data model."""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Status(enum.StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    PENDING = "pending"  # evidence not there *yet* (CI still running, reviewer not yet verified)
    SKIP = "skip"  # not applicable in this mode
    ERROR = "error"  # check crashed or is misconfigured


class Severity(enum.StrEnum):
    BLOCK = "block"
    WARN = "warn"


class Match(BaseModel):
    """When a rule applies. All populated fields must match (AND); lists are OR within."""

    model_config = ConfigDict(extra="forbid")

    always: bool = False
    paths: list[str] = Field(default_factory=list, description="Globs; any changed file matches")
    exclude_paths: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list, description="Any of these PR labels present")
    title: str | None = Field(default=None, description="Regex tested against the PR title")
    base_branches: list[str] = Field(default_factory=list, description="Globs on the base branch")
    authors: list[str] = Field(
        default_factory=list, description="PR author logins (e.g. bot accounts) this rule applies to"
    )


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    check: str
    id: str | None = None
    name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict, alias="with")
    severity: Severity | None = None
    instructions: str | None = None

    @property
    def key(self) -> str:
        return self.id or self.name or self.check


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    when: Match = Field(default_factory=lambda: Match(always=True))
    severity: Severity = Severity.BLOCK
    require: list[Requirement]
    instructions: str | None = None

    @model_validator(mode="after")
    def _unique_requirement_keys(self) -> Rule:
        seen: set[str] = set()
        for req in self.require:
            if req.key in seen:
                raise ValueError(
                    f"rule {self.id!r}: duplicate requirement key {req.key!r}; "
                    "give each a distinct `name` or `id` when using the same check twice"
                )
            seen.add(req.key)
        return self


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    project: str | None = None
    evidence_block: str = Field(
        default="evidence",
        description="Info-string of the fenced code block in the PR body that carries evidence",
    )
    rules: list[Rule]
    settings: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> Policy:
        ids = [r.id for r in self.rules]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate rule ids: {sorted(dupes)}")
        return self


class CheckResult(BaseModel):
    status: Status
    summary: str
    details: list[str] = Field(default_factory=list)
    fix: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class RequirementReport(BaseModel):
    rule_id: str
    key: str
    check: str
    name: str
    severity: Severity
    result: CheckResult
    instructions: str | None = None
    evidence_template: dict[str, Any] = Field(default_factory=dict)


class RuleReport(BaseModel):
    rule_id: str
    description: str
    severity: Severity
    matched: bool
    matched_files: list[str] = Field(default_factory=list)
    instructions: str | None = None
    requirements: list[RequirementReport] = Field(default_factory=list)


class Report(BaseModel):
    project: str | None = None
    repo: str | None = None
    number: int | None = None
    head_sha: str | None = None
    mode: str = "local"
    rules: list[RuleReport]

    @property
    def matched_rules(self) -> list[RuleReport]:
        return [r for r in self.rules if r.matched]

    def requirement_reports(self) -> list[RequirementReport]:
        return [q for r in self.matched_rules for q in r.requirements]

    @property
    def verdict(self) -> Status:
        reqs = self.requirement_reports()
        blocking = [q for q in reqs if q.severity == Severity.BLOCK]
        if any(q.result.status in (Status.FAIL, Status.ERROR) for q in blocking):
            return Status.FAIL
        if any(q.result.status == Status.PENDING for q in blocking):
            return Status.PENDING
        if any(q.result.status in (Status.FAIL, Status.ERROR, Status.WARN, Status.PENDING) for q in reqs):
            return Status.WARN
        return Status.PASS

    def evidence_template(self) -> dict[str, Any]:
        """Merged evidence block skeleton for every unmet evidence requirement."""
        merged: dict[str, Any] = {}
        for q in self.requirement_reports():
            if q.result.status in (Status.PASS, Status.SKIP):
                continue
            _deep_merge(merged, q.evidence_template)
        return merged


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst.setdefault(k, v)
