"""Markdown renderers: the PR comment, the local `explain` view, and the agent prompt."""

from __future__ import annotations

from ..engine import default_registry
from ..evidence import render_template
from ..models import Policy, Report, Severity, Status

MARKER = "<!-- mergeproof-report -->"

ICON = {
    Status.PASS: "✅",
    Status.FAIL: "❌",
    Status.WARN: "⚠️",
    Status.PENDING: "⏳",
    Status.SKIP: "⏭️",
    Status.ERROR: "💥",
}

VERDICT_TEXT = {
    Status.PASS: "all evidence present",
    Status.FAIL: "evidence missing",
    Status.PENDING: "waiting for evidence",
    Status.WARN: "passing with warnings",
}


def render_report(report: Report, evidence_tag: str = "evidence", include_marker: bool = True) -> str:
    v = report.verdict
    lines: list[str] = []
    if include_marker:
        lines.append(MARKER)
    title = f"## {ICON[v]} Mergeproof — {VERDICT_TEXT.get(v, v.value)}"
    if report.head_sha:
        title += f" <sub>`{report.head_sha[:7]}`</sub>"
    lines += [title, ""]

    matched = report.matched_rules
    if not matched:
        lines.append("No rules apply to this change.")
        return "\n".join(lines)

    lines += ["| Rule | Requirement | Status | Detail |", "|---|---|:-:|---|"]
    for rr in matched:
        for q in rr.requirements:
            sev = "" if q.severity == Severity.BLOCK else " <sub>(warn)</sub>"
            lines.append(f"| `{rr.rule_id}` | {q.name}{sev} | {ICON[q.result.status]} | {q.result.summary} |")
    lines.append("")

    unmet = [(rr, q) for rr in matched for q in rr.requirements if q.result.status not in (Status.PASS, Status.SKIP)]
    if unmet:
        lines += ["### What is still needed", ""]
        for rr, q in unmet:
            lines.append(f"**{q.name}** (`{rr.rule_id}`) — {q.result.summary}")
            for d in q.result.details:
                lines.append(f"- {d}")
            if q.result.fix:
                lines.append(f"- **Fix:** {q.result.fix}")
            if q.instructions or rr.instructions:
                lines.append(f"- {q.instructions or rr.instructions}")
            lines.append("")
        tmpl = report.evidence_template()
        if tmpl:
            lines += [
                "<details><summary>Evidence template — paste into the PR description and fill in</summary>",
                "",
                render_template(tmpl, evidence_tag),
                "",
                "</details>",
                "",
            ]

    lines.append(
        f"<sub>Run `mergeproof explain` locally to see these requirements before pushing · mode: {report.mode}</sub>"
    )
    return "\n".join(lines)


def render_explain(report: Report, policy: Policy) -> str:
    """Local, agent-facing view: what this diff must prove and what is missing right now."""
    reg = default_registry()
    lines = [f"# Mergeproof — what this change must prove ({report.verdict.value})", ""]
    matched = report.matched_rules
    if not matched:
        lines.append("No rules apply to the current diff.")
        return "\n".join(lines)
    rules_by_id = {r.id: r for r in policy.rules}
    for rr in matched:
        rule = rules_by_id[rr.rule_id]
        lines += [f"## {rr.rule_id}  [{rr.severity.value}]", ""]
        if rr.description:
            lines += [rr.description, ""]
        if rr.matched_files:
            shown = rr.matched_files[:8]
            more = f" (+{len(rr.matched_files) - 8} more)" if len(rr.matched_files) > 8 else ""
            lines += ["Triggered by: " + ", ".join(f"`{f}`" for f in shown) + more, ""]
        for req, q in zip(rule.require, rr.requirements, strict=True):
            check = reg.get(req.check)
            params = check.parse_params(req.params)
            lines.append(f"- {ICON[q.result.status]} **{q.name}** — {check.explain(params)}")
            lines.append(f"  - now: {q.result.summary}")
            for d in q.result.details[:6]:
                lines.append(f"  - {d}")
            if q.result.fix and q.result.status not in (Status.PASS, Status.SKIP):
                lines.append(f"  - fix: {q.result.fix}")
            if req.instructions or rule.instructions:
                lines.append(f"  - note: {req.instructions or rule.instructions}")
        lines.append("")
    tmpl = report.evidence_template()
    if tmpl:
        lines += [
            "## Evidence block to add to the PR description",
            "",
            render_template(tmpl, policy.evidence_block),
            "",
        ]
    return "\n".join(lines)


def render_agent_prompt(policy: Policy) -> str:
    """A Markdown section for CLAUDE.md / AGENTS.md generated from the policy, so agents read the
    exact rules CI will enforce."""
    reg = default_registry()
    lines = [
        "## Evidence requirements (enforced in CI by mergeproof)",
        "",
        "Every pull request is gated on evidence, not just green tests. Before opening or updating a PR, "
        "run `mergeproof explain` and satisfy every listed requirement. Evidence goes in a fenced "
        f"```{policy.evidence_block} block in the PR description.",
        "",
    ]
    for rule in policy.rules:
        w = rule.when
        conds = []
        if w.paths:
            conds.append("files matching " + ", ".join(f"`{p}`" for p in w.paths))
        if w.exclude_paths:
            conds.append("except " + ", ".join(f"`{p}`" for p in w.exclude_paths))
        if w.labels:
            conds.append("label " + " or ".join(f"`{lbl}`" for lbl in w.labels))
        if w.title:
            conds.append(f"title matching `{w.title}`")
        if w.base_branches:
            conds.append("targeting " + ", ".join(f"`{b}`" for b in w.base_branches))
        if w.authors:
            conds.append("authored by " + " or ".join(f"`{a}`" for a in w.authors))
        when = "; ".join(conds) if conds else "every change"
        lines += [
            f"### `{rule.id}` — {rule.description or 'no description'}",
            "",
            f"**When:** {when}. **Severity:** {rule.severity.value}.",
            "",
        ]
        if rule.instructions:
            lines += [rule.instructions.strip(), ""]
        template: dict = {}
        for req in rule.require:
            check = reg.get(req.check)
            params = check.parse_params(req.params)
            label = req.name or req.key
            lines.append(f"- **{label}** — {check.explain(params)}")
            if req.instructions:
                lines.append(f"  - {req.instructions.strip()}")
            for k, v in check.evidence_template(params).items():
                template.setdefault(k, v)
        lines.append("")
        if template:
            lines += ["Evidence block for this rule:", "", render_template(template, policy.evidence_block), ""]
    lines += [
        "### Rules for agents",
        "",
        "- Never fabricate evidence. If you cannot produce a required artifact (e.g. a live trace), say so in "
        "the PR and leave the field out; the gate will stay pending for a human.",
        "- `review.human_verified` requirements can only be satisfied by a human reviewer other than the "
        "author. Do not attempt to post the verification phrase.",
        "- Keep the evidence block machine-readable YAML; do not wrap links in extra Markdown.",
    ]
    return "\n".join(lines)
