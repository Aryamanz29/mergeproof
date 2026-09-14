"""Match rules against a context and run their checks."""

from __future__ import annotations

import re

from pydantic import ValidationError

from mergeproof import patterns
from mergeproof.checks.registry import Registry
from mergeproof.context import Context
from mergeproof.policy import Policy, Requirement, Rule, When
from mergeproof.report import Outcome, Report, RequirementResult, RuleResult, Status


def applies(when: When, ctx: Context) -> tuple[bool, list[str]]:
    """Return whether *when* matches *ctx* and the changed paths that triggered it."""
    files = ctx.changed_paths
    if when.paths:
        files = patterns.select(files, when.paths, when.exclude_paths)
        if not files:
            return False, []
    elif when.exclude_paths:
        files = [f for f in files if not patterns.matches_any(when.exclude_paths, f)]
    if when.labels and not set(when.labels) & set(ctx.labels):
        return False, []
    if when.title and not re.search(when.title, ctx.title, re.I):
        return False, []
    if when.base_branches and not patterns.matches_any(when.base_branches, ctx.base_ref):
        return False, []
    if when.authors and ctx.author not in when.authors:
        return False, []
    return True, files


def evaluate(policy: Policy, ctx: Context, registry: Registry) -> Report:
    report = Report(
        project=policy.project,
        evidence_block=policy.evidence_block,
        source=ctx.source,
        repo=ctx.repo,
        number=ctx.number,
        head_sha=ctx.head_sha,
        base_ref=ctx.base_ref,
        merged=ctx.merged,
        merge_commit_sha=ctx.merge_commit_sha,
        merged_at=ctx.merged_at,
        merged_by=ctx.merged_by,
    )
    for rule in policy.rules:
        matched, files = applies(rule.when, ctx)
        result = RuleResult(
            id=rule.id,
            description=rule.description,
            severity=rule.severity,
            matched=matched,
            files=files,
            instructions=rule.instructions,
        )
        if matched:
            result.requirements = [run_requirement(rule, req, ctx, files, registry) for req in rule.require]
        report.rules.append(result)
    return report


def run_requirement(
    rule: Rule, req: Requirement, ctx: Context, files: list[str], registry: Registry
) -> RequirementResult:
    result = RequirementResult(
        label=req.label,
        check=req.check,
        severity=req.severity or rule.severity,
        instructions=req.instructions or rule.instructions,
        outcome=Outcome(status=Status.ERROR, summary="not run"),
    )
    check = registry.lookup(req.check)
    if check is None:
        result.outcome.summary = f"unknown check {req.check!r}"
        return result
    try:
        params = check.parse_params(req.params)
    except ValidationError as exc:
        result.outcome.summary = f"bad parameters: {exc.errors()[0]['msg']}"
        return result
    try:
        result.outcome = check.run(ctx, params, files)
    except Exception as exc:  # a broken check must not take the whole gate down
        result.outcome = Outcome(status=Status.ERROR, summary=f"{type(exc).__name__}: {exc}")
    result.evidence_template = check.evidence_template(params)
    return result
