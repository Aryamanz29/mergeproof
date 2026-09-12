"""Match rules against a PR and run their checks."""

from __future__ import annotations

import re
from typing import Any

import yaml
from pydantic import ValidationError

from . import patterns
from .checks.registry import Registry, UnknownCheck, default_registry
from .context import PRContext
from .models import (
    CheckResult,
    Match,
    Policy,
    Report,
    RequirementReport,
    Rule,
    RuleReport,
    Status,
)


class PolicyError(ValueError):
    pass


def load_policy(path: str) -> Policy:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    try:
        return Policy.model_validate(raw)
    except ValidationError as exc:
        raise PolicyError(f"{path}: {exc}") from None


def validate_policy(policy: Policy, registry: Registry | None = None) -> list[str]:
    """Return human-readable problems (unknown checks, bad params). Empty list = OK."""
    registry = registry or default_registry()
    problems: list[str] = []
    for rule in policy.rules:
        for req in rule.require:
            try:
                check = registry.get(req.check)
            except UnknownCheck as exc:
                problems.append(f"rule {rule.id!r} / {req.key!r}: {exc}")
                continue
            try:
                check.parse_params(req.params)
            except ValidationError as exc:
                problems.append(f"rule {rule.id!r} / {req.key!r}: invalid `with`: {exc}")
    return problems


def match_rule(when: Match, ctx: PRContext) -> tuple[bool, list[str]]:
    files = ctx.changed_paths
    if when.paths:
        files = patterns.filter_paths(files, when.paths, when.exclude_paths)
        if not files:
            return False, []
    elif when.exclude_paths:
        files = [f for f in files if not patterns.any_match(when.exclude_paths, f)]
    if when.labels and not set(when.labels) & set(ctx.labels):
        return False, []
    if when.title and not re.search(when.title, ctx.title or "", re.I):
        return False, []
    if when.base_branches and not patterns.any_match(when.base_branches, ctx.base_ref):
        return False, []
    if when.authors and ctx.author not in when.authors:
        return False, []
    if not (when.always or when.paths or when.labels or when.title or when.base_branches or when.authors):
        # Empty matcher == always (a rule with no `when`)
        return True, files
    return True, files


def _run_requirement(rule: Rule, req: Any, ctx: PRContext, files: list[str], registry: Registry) -> RequirementReport:
    severity = req.severity or rule.severity
    name = req.name or req.key
    try:
        check = registry.get(req.check)
        params = check.parse_params(req.params)
    except (UnknownCheck, ValidationError) as exc:
        return RequirementReport(
            rule_id=rule.id,
            key=req.key,
            check=req.check,
            name=name,
            severity=severity,
            result=CheckResult(status=Status.ERROR, summary=f"misconfigured: {exc}"),
            instructions=req.instructions,
        )
    try:
        result = check.run(ctx, params, files)
    except Exception as exc:  # noqa: BLE001 - a crashing check must not take the gate down
        result = CheckResult(status=Status.ERROR, summary=f"{type(exc).__name__}: {exc}")
    template: dict[str, Any] = {}
    try:
        template = check.evidence_template(params)
    except Exception:  # noqa: BLE001
        pass
    return RequirementReport(
        rule_id=rule.id,
        key=req.key,
        check=req.check,
        name=name,
        severity=severity,
        result=result,
        instructions=req.instructions,
        evidence_template=template,
    )


def evaluate(policy: Policy, ctx: PRContext, registry: Registry | None = None) -> Report:
    registry = registry or default_registry()
    rule_reports: list[RuleReport] = []
    for rule in policy.rules:
        matched, files = match_rule(rule.when, ctx)
        rr = RuleReport(
            rule_id=rule.id,
            description=rule.description,
            severity=rule.severity,
            matched=matched,
            matched_files=files,
            instructions=rule.instructions,
        )
        if matched:
            rr.requirements = [_run_requirement(rule, req, ctx, files, registry) for req in rule.require]
        rule_reports.append(rr)
    return Report(
        project=policy.project,
        repo=ctx.repo,
        number=ctx.number,
        head_sha=ctx.head_sha,
        mode=ctx.mode,
        rules=rule_reports,
    )
