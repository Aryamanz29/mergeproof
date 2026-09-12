"""A Markdown section for CLAUDE.md / AGENTS.md generated from the policy."""

from __future__ import annotations

from typing import Any

from mergeproof import evidence
from mergeproof.checks.registry import Registry
from mergeproof.policy import Policy, When


def describe_when(when: When) -> str:
    conditions = []
    if when.paths:
        conditions.append("files matching " + ", ".join(f"`{p}`" for p in when.paths))
    if when.exclude_paths:
        conditions.append("except " + ", ".join(f"`{p}`" for p in when.exclude_paths))
    if when.labels:
        conditions.append("label " + " or ".join(f"`{lbl}`" for lbl in when.labels))
    if when.title:
        conditions.append(f"title matching `{when.title}`")
    if when.base_branches:
        conditions.append("targeting " + ", ".join(f"`{b}`" for b in when.base_branches))
    if when.authors:
        conditions.append("authored by " + " or ".join(f"`{a}`" for a in when.authors))
    return "; ".join(conditions) if conditions else "every change"


def agent_prompt(policy: Policy, registry: Registry) -> str:
    lines = [
        "## Evidence requirements (enforced in CI by mergeproof)",
        "",
        "Pull requests are gated on evidence, not on claims. Before opening or updating a PR run "
        "`mergeproof explain` and satisfy every listed requirement. Evidence goes in a fenced "
        f"```{policy.evidence_block} block in the PR description.",
        "",
    ]
    for rule in policy.rules:
        lines += [
            f"### `{rule.id}`: {rule.description or 'no description'}",
            "",
            f"**When:** {describe_when(rule.when)}. **Severity:** {rule.severity.value}.",
            "",
        ]
        if rule.instructions:
            lines += [rule.instructions.strip(), ""]
        templates: list[dict[str, Any]] = []
        for req in rule.require:
            check = registry.lookup(req.check)
            if check is None:
                lines.append(f"- **{req.label}**: unknown check `{req.check}`")
                continue
            params = check.parse_params(req.params)
            lines.append(f"- **{req.label}**: {check.explain(params)}")
            if req.instructions:
                lines.append(f"  - {req.instructions.strip()}")
            templates.append(check.evidence_template(params))
        lines.append("")
        merged = evidence.merge_templates(templates)
        if merged:
            lines += ["Evidence block for this rule:", "", evidence.render(merged, policy.evidence_block), ""]
    lines += [
        "### Rules for agents",
        "",
        "- Never fabricate evidence. If you cannot produce a required artifact, say so in the PR and leave "
        "the field out; the gate stays pending until a human decides.",
        "- Requirements of type `review.human_verified` can only be satisfied by a human other than the "
        "author. Do not post the verification phrase.",
        "- Keep the evidence block plain YAML. Do not wrap links in extra Markdown.",
    ]
    return "\n".join(lines)
