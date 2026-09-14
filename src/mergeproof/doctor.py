"""`mergeproof doctor`: is this repository set up so the gate can do its job?

Most support questions so far were configuration: a missing permission, an
event the workflow did not subscribe to, a status nobody required. Each
cost a round trip. The doctor reads the policy, the workflow files and,
when a token is available, the branch rules, and prints what is wrong with
the fix next to it. It reports only what it looked at.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from mergeproof import policy as policy_module
from mergeproof.checks.registry import Registry
from mergeproof.providers.github import Client
from mergeproof.verifiers import UnknownVerifier, load_verifier

ACTION = "Aryamanz29/mergeproof"
PR_TYPES = ("opened", "synchronize", "reopened", "edited", "labeled", "unlabeled")
DEFAULT_PR_TYPES = ("opened", "synchronize", "reopened")
COMMENT_CHECKS = {"review.human_verified", "agent.verdict"}
CHECK_RUN_CHECKS = {"ci.job_passed"}
PINNED = re.compile(r"^(v\d+(\.\d+)*|[0-9a-f]{40})$")
EXAMPLE = "https://github.com/Aryamanz29/mergeproof/blob/main/examples/github-workflow.yml"
PR_NUMBER_ENV = "MERGEPROOF_PR_NUMBER: ${{ github.event.issue.number || github.event.pull_request.number }}"
RANK = {"none": 0, "read": 1, "write": 2}


@dataclass
class Finding:
    level: str  # ok, warn, error
    area: str  # policy, workflow, repository
    message: str
    fix: str = ""


@dataclass
class Needs:
    """What the policy asks of the workflow."""

    comments: bool = False
    check_suite: bool = False
    checks: set[str] = field(default_factory=set)


class Findings(list[Finding]):
    def add(self, level: str, area: str, message: str, fix: str = "") -> None:
        self.append(Finding(level, area, message, fix))


def run(
    policy_path: str, registry: Registry, root: str | Path = ".", repo: str | None = None, client: Client | None = None
) -> list[Finding]:
    findings = Findings()
    pol = check_policy(policy_path, registry, findings)
    needs = needs_of(pol) if pol is not None else Needs()
    check_workflows(Path(root), needs, findings)
    if client is None:
        findings.add("warn", "repository", "branch rules not checked: no GITHUB_TOKEN", "export GITHUB_TOKEN and rerun")
    elif not repo:
        findings.add("warn", "repository", "branch rules not checked: repository unknown", "pass --repo OWNER/NAME")
    else:
        check_repository(client, repo, findings)
    return list(findings)


def check_policy(path: str, registry: Registry, findings: Findings) -> policy_module.Policy | None:
    try:
        pol = policy_module.load(path)
    except policy_module.PolicyError as exc:
        findings.add("error", "policy", str(exc), "fix the policy; `mergeproof validate` shows the same")
        return None
    problems = policy_module.problems(pol, registry)
    for problem in problems:
        findings.add("error", "policy", problem, "`mergeproof checks` lists the parameters each check takes")
    if not problems:
        findings.add("ok", "policy", f"{path}: {len(pol.rules)} rule(s), every check known")
    for rule in pol.rules:
        for req in rule.require:
            check = registry.lookup(req.check)
            if check is None or "verify" not in check.Params.model_fields:
                continue
            try:
                name = getattr(check.parse_params(req.params), "verify", None)
            except Exception:
                continue
            if not name:
                continue
            try:
                load_verifier(name, {})
            except UnknownVerifier:
                findings.add(
                    "error",
                    "policy",
                    f"rule {rule.id!r} verifies links with `{name}`, which is not installed",
                    "add the plugin that provides it to the action's `plugins` input, or pip install it locally",
                )
            except Exception as exc:
                findings.add(
                    "warn",
                    "policy",
                    f"verifier `{name}` (rule {rule.id!r}) is installed but did not start here: {exc}",
                    "expected locally when its credentials only exist in CI; make sure the workflow sets them",
                )
            else:
                findings.add("ok", "policy", f"verifier `{name}` (rule {rule.id!r}) is installed")
    return pol


def needs_of(pol: policy_module.Policy) -> Needs:
    needs = Needs()
    for rule in pol.rules:
        for req in rule.require:
            needs.checks.add(req.check)
            needs.comments = needs.comments or req.check in COMMENT_CHECKS
            needs.check_suite = needs.check_suite or req.check in CHECK_RUN_CHECKS
    return needs


def workflows_using_the_action(root: Path) -> list[tuple[Path, dict[str, Any], list[dict[str, Any]]]]:
    """Every workflow file with a step that uses the action, and those steps with their job."""
    found = []
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict):
            continue
        steps = []
        for job in (doc.get("jobs") or {}).values():
            for step in (job or {}).get("steps") or []:
                uses = str((step or {}).get("uses") or "")
                if uses.startswith(ACTION) or uses == "./":
                    steps.append({"job": job, "step": step, "uses": uses})
        if steps:
            found.append((path, doc, steps))
    return found


def triggers(doc: dict[Any, Any]) -> dict[str, Any]:
    on = doc.get("on")
    if on is None:
        on = doc.get(True)  # YAML 1.1 reads a bare `on:` key as the boolean True
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return dict.fromkeys(on)
    return dict(on or {})


def permissions_of(doc: dict[str, Any], job: dict[str, Any]) -> dict[str, str] | None:
    perms: Any = job.get("permissions")
    if perms is None:
        perms = doc.get("permissions")
    if perms is None:
        return None
    if isinstance(perms, str):
        return {"*": perms}
    return {str(k): str(v) for k, v in dict(perms).items()}


def env_of(doc: dict[str, Any], job: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for scope in (doc, job, step):
        merged.update(scope.get("env") or {})
    return merged


def check_workflows(root: Path, needs: Needs, findings: Findings) -> None:
    using = workflows_using_the_action(root)
    if not using:
        where = root / ".github" / "workflows"
        findings.add("error", "workflow", f"no workflow under {where} uses {ACTION}", f"copy {EXAMPLE} there")
        return
    for path, doc, steps in using:
        name = str(path.relative_to(root))
        on = triggers(doc)
        for entry in steps:
            job, step, uses = entry["job"], entry["step"], entry["uses"]
            inputs = {str(k): str(v).lower() for k, v in ((step.get("with") or {}).items())}
            receipts = inputs.get("receipt", "true") != "false"
            check_action_ref(name, uses, findings)
            if receipt_only(on, inputs):
                findings.add("ok", "workflow", f"{name}: receipt companion (runs on `closed` only, posts no status)")
                check_permissions(name, permissions_of(doc, job), inputs, needs, receipts, findings)
                continue
            check_pull_request_events(name, on, receipts, findings)
            check_event_subscriptions(name, on, needs, findings)
            if ("issue_comment" in on or "check_suite" in on) and "MERGEPROOF_PR_NUMBER" not in env_of(doc, job, step):
                findings.add(
                    "error",
                    "workflow",
                    f"{name}: runs on comment or check-suite events without MERGEPROOF_PR_NUMBER",
                    f"add to the action step: `env:` with `{PR_NUMBER_ENV}`",
                )
            check_permissions(name, permissions_of(doc, job), inputs, needs, receipts, findings)
            check_checkout(name, job, findings)


def receipt_only(on: dict[str, Any], inputs: dict[str, str]) -> bool:
    """A second workflow that exists only to write the receipt when the PR merges; the gate lives elsewhere."""
    pr = on.get("pull_request")
    types = list((pr or {}).get("types") or []) if isinstance(pr, dict) else []
    return types == ["closed"] and inputs.get("status", "true") == "false"


def check_action_ref(name: str, uses: str, findings: Findings) -> None:
    if uses == "./":
        findings.add("ok", "workflow", f"{name}: uses the action from this repository")
        return
    ref = uses.split("@", 1)[1] if "@" in uses else ""
    if PINNED.match(ref):
        findings.add("ok", "workflow", f"{name}: action pinned to {ref}")
    else:
        findings.add(
            "error",
            "workflow",
            f"{name}: action ref {ref or '(none)'!r} is a branch or missing",
            f"use `{ACTION}@v0` (floating major), a release tag, or a commit sha",
        )


def check_pull_request_events(name: str, on: dict[str, Any], receipts: bool, findings: Findings) -> None:
    if "pull_request" not in on:
        fix = f"add `pull_request:` with `types: [{', '.join(PR_TYPES)}]` under `on:`"
        findings.add("error", "workflow", f"{name}: does not run on pull_request", fix)
        return
    pr = on["pull_request"]
    types = list((pr or {}).get("types") or DEFAULT_PR_TYPES) if isinstance(pr, dict) or pr is None else []
    missing = [t for t in PR_TYPES if t not in types]
    if missing:
        findings.add(
            "warn",
            "workflow",
            f"{name}: pull_request types miss {', '.join(missing)}",
            "list them under `pull_request: types:`; without `edited` an evidence block added later is not seen, "
            "without the label events label-gated rules lag a push behind",
        )
    else:
        findings.add("ok", "workflow", f"{name}: pull_request types cover pushes, edits and labels")
    if receipts and "closed" not in types:
        findings.add(
            "warn",
            "workflow",
            f"{name}: receipts are on but the workflow does not run on pull_request `closed`",
            'add `closed` to `pull_request: types:`, or set `receipt: "false"`',
        )


def check_event_subscriptions(name: str, on: dict[str, Any], needs: Needs, findings: Findings) -> None:
    if needs.comments:
        if "issue_comment" in on:
            findings.add("ok", "workflow", f"{name}: subscribes to issue_comment")
        else:
            which = ", ".join(sorted(needs.checks & COMMENT_CHECKS))
            findings.add(
                "error",
                "workflow",
                f"{name}: the policy reads comments ({which}) but the workflow does not run on issue_comment",
                "add `issue_comment:` with `types: [created, edited]` under `on:`; "
                "verification would otherwise wait for the next push",
            )
    if needs.check_suite:
        if "check_suite" in on:
            findings.add("ok", "workflow", f"{name}: subscribes to check_suite")
        else:
            findings.add(
                "warn",
                "workflow",
                f"{name}: the policy reads CI results (ci.job_passed) but the workflow does not run on check_suite",
                "add `check_suite:` with `types: [completed]` under `on:` so the gate re-evaluates when CI finishes",
            )


def check_permissions(
    name: str, perms: dict[str, str] | None, inputs: dict[str, str], needs: Needs, receipts: bool, findings: Findings
) -> None:
    if perms is None:
        findings.add(
            "warn",
            "workflow",
            f"{name}: no `permissions:` block; the job runs with the repository's default token permissions",
            "set them explicitly: contents read, pull-requests write, statuses write, checks read",
        )
        return
    if "*" in perms:
        findings.add("ok", "workflow", f"{name}: permissions: {perms['*']}")
        return
    wanted: list[tuple[str, str, str, str]] = []
    if inputs.get("comment", "true") != "false" or inputs.get("review-comments", "true") != "false":
        wanted.append(("pull-requests", "write", "error", "the comment and review comments"))
    if inputs.get("status", "true") != "false":
        wanted.append(("statuses", "write", "error", "the `mergeproof` commit status, the one to require"))
    if needs.check_suite:
        wanted.append(("checks", "read", "error", "reading other jobs' results for ci.job_passed"))
    if receipts:
        wanted.append(("contents", "write", "warn", "writing receipts; without it the action logs and skips them"))
    for scope, level, severity, why in wanted:
        have = perms.get(scope, "none")
        if RANK.get(have, 0) >= RANK[level]:
            findings.add("ok", "workflow", f"{name}: {scope}: {have} covers {why}")
        else:
            message = f"{name}: `{scope}: {level}` is missing; needed for {why}"
            findings.add(severity, "workflow", message, f"add `{scope}: {level}` to the job's `permissions:`")
    if perms.get("checks") == "write":
        message = f"{name}: `checks: write` is no longer needed (the Check Run option was removed in 0.8)"
        findings.add("warn", "workflow", message, "change it to `checks: read`")


def check_checkout(name: str, job: dict[str, Any], findings: Findings) -> None:
    for step in job.get("steps") or []:
        uses = str((step or {}).get("uses") or "")
        if not uses.startswith("actions/checkout"):
            continue
        ref = str(((step or {}).get("with") or {}).get("ref") or "")
        if "default_branch" in ref or ref in ("main", "master") or ref.startswith("refs/heads/"):
            findings.add("ok", "workflow", f"{name}: policy is read from the base branch")
        else:
            findings.add(
                "warn",
                "workflow",
                f"{name}: checkout has no base-branch `ref`, so a pull request could edit the policy that gates it",
                "give actions/checkout `with:` `ref: ${{ github.event.repository.default_branch }}`",
            )
        return


def required_contexts(client: Client, repo: str, branch: str) -> tuple[set[str], str | None]:
    """Status contexts required on *branch*, from a ruleset first, classic protection second."""
    contexts: set[str] = set()
    try:
        for rule in client.get(f"/repos/{repo}/rules/branches/{branch}"):
            if rule.get("type") == "required_status_checks":
                for entry in (rule.get("parameters") or {}).get("required_status_checks") or []:
                    contexts.add(str(entry.get("context")))
                return contexts, "ruleset"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (403, 404):
            raise
    try:
        data = client.get(f"/repos/{repo}/branches/{branch}/protection/required_status_checks")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (403, 404):
            raise
        return contexts, None
    contexts.update(str(c) for c in data.get("contexts") or [])
    contexts.update(str(c.get("context")) for c in data.get("checks") or [])
    return contexts, "branch protection"


def check_repository(client: Client, repo: str, findings: Findings) -> None:
    try:
        branch = str(client.get(f"/repos/{repo}").get("default_branch") or "main")
    except httpx.HTTPError as exc:
        findings.add("warn", "repository", f"could not read {repo}: {exc}", "check the token and the repository name")
        return
    contexts, source = required_contexts(client, repo, branch)
    if source is None:
        findings.add(
            "warn",
            "repository",
            f"{repo}: could not read the rules protecting {branch} (none visible to this token)",
            "require the `mergeproof` status on the default branch in a ruleset; the GitHub guide has the API call",
        )
    elif "mergeproof" in contexts:
        findings.add("ok", "repository", f"{repo}: `mergeproof` status is required on {branch} ({source})")
    else:
        required = ", ".join(sorted(contexts)) or "nothing"
        findings.add(
            "error",
            "repository",
            f"{repo}: the `mergeproof` status is not required on {branch} ({source} requires {required})",
            "add the `mergeproof` context to the required status checks; until then the gate only reports",
        )


def render_text(findings: list[Finding]) -> str:
    lines = []
    for f in findings:
        lines.append(f"[{f.level:>5}] {f.area}: {f.message}")
        if f.fix and f.level != "ok":
            lines.append(f"        fix: {f.fix}")
    errors = sum(1 for f in findings if f.level == "error")
    warns = sum(1 for f in findings if f.level == "warn")
    verdict = "everything looks right" if not errors and not warns else f"{errors} error(s), {warns} warning(s)"
    return "\n".join([*lines, "", verdict]) + "\n"


def to_json(findings: list[Finding]) -> list[dict[str, str]]:
    return [asdict(f) for f in findings]


def worst(findings: list[Finding]) -> int:
    return 1 if any(f.level == "error" for f in findings) else 0
