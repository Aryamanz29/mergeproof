"""The policy file: rules of the form "when a change touches X it must prove Y"."""

from __future__ import annotations

import enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

if TYPE_CHECKING:
    from mergeproof.checks.registry import Registry


class Severity(enum.StrEnum):
    BLOCK = "block"
    WARN = "warn"


class When(BaseModel):
    """Conditions under which a rule applies. Fields combine with AND, list items with OR."""

    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    title: str | None = None
    base_branches: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)

    def is_unconditional(self) -> bool:
        return not (self.paths or self.labels or self.title or self.base_branches or self.authors)


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    check: str
    name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict, alias="with")
    severity: Severity | None = None
    instructions: str | None = None

    @property
    def label(self) -> str:
        return self.name or self.check


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    when: When = Field(default_factory=When)
    severity: Severity = Severity.BLOCK
    require: list[Requirement] = Field(min_length=1)
    instructions: str | None = None

    @model_validator(mode="after")
    def labels_are_unique(self) -> Rule:
        seen: set[str] = set()
        for req in self.require:
            if req.label in seen:
                raise ValueError(f"rule {self.id!r} uses {req.label!r} twice; give each requirement a distinct `name`")
            seen.add(req.label)
        return self


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    project: str | None = None
    evidence_block: str = "evidence"
    rules: list[Rule] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_are_unique(self) -> Policy:
        ids = [r.id for r in self.rules]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate rule ids: {', '.join(dupes)}")
        return self


class PolicyError(ValueError):
    pass


def loads(text: str, source: str = "<policy>") -> Policy:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyError(f"{source}: not valid YAML: {exc}") from None
    if raw is None:
        raise PolicyError(f"{source}: empty policy")
    try:
        return Policy.model_validate(raw)
    except ValidationError as exc:
        raise PolicyError(f"{source}: {_format_validation(exc)}") from None


def load(path: str | Path) -> Policy:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PolicyError(f"{path}: not found (run `mergeproof init`)") from None
    return loads(text, str(path))


def problems(policy: Policy, registry: Registry) -> list[str]:
    """Semantic problems the schema cannot see: unknown checks and bad `with` blocks."""
    found: list[str] = []
    for rule in policy.rules:
        for req in rule.require:
            check = registry.lookup(req.check)
            if check is None:
                found.append(f"rule {rule.id!r} / {req.label!r}: unknown check {req.check!r}")
                continue
            try:
                check.parse_params(req.params)
            except ValidationError as exc:
                found.append(f"rule {rule.id!r} / {req.label!r}: {_format_validation(exc)}")
    return found


def _format_validation(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"]) or "policy"
        lines.append(f"{where}: {err['msg']}")
    return "; ".join(lines)
