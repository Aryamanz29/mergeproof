import json
import textwrap

import httpx
import respx

from mergeproof import doctor
from mergeproof.checks.registry import builtin_registry
from mergeproof.providers import github

API = "https://api.github.com"
POLICY = textwrap.dedent(
    """
    rules:
      - id: src
        when: { paths: ["src/**"] }
        require:
          - check: tests.changed
            with: { any_of: ["tests/**"] }
          - check: ci.job_passed
            with: { name: unit }
          - check: review.human_verified
    """
)
GOOD_WORKFLOW = textwrap.dedent(
    """
    on:
      pull_request:
        types: [opened, synchronize, reopened, edited, labeled, unlabeled, closed]
      issue_comment: { types: [created, edited] }
      check_suite: { types: [completed] }
    jobs:
      gate:
        runs-on: ubuntu-latest
        permissions: { contents: write, pull-requests: write, statuses: write, checks: read }
        steps:
          - uses: actions/checkout@v4
            with:
              ref: ${{ github.event.repository.default_branch }}
          - uses: Aryamanz29/mergeproof@v0
            env:
              MERGEPROOF_PR_NUMBER: ${{ github.event.issue.number || github.event.pull_request.number }}
    """
)
SLOPPY_WORKFLOW = textwrap.dedent(
    """
    on: [pull_request]
    jobs:
      gate:
        runs-on: ubuntu-latest
        permissions: { contents: read, pull-requests: write, checks: write }
        steps:
          - uses: actions/checkout@v4
          - uses: Aryamanz29/mergeproof@main
    """
)


def repo_with(tmp_path, workflow, policy=POLICY):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "mergeproof.yml").write_text(workflow)
    (tmp_path / "mergeproof.yaml").write_text(policy)
    return tmp_path


def levels(findings, area=None):
    return [(f.level, f.message) for f in findings if area is None or f.area == area]


def test_a_correct_setup_has_no_errors(tmp_path):
    root = repo_with(tmp_path, GOOD_WORKFLOW)
    findings = doctor.run(str(root / "mergeproof.yaml"), builtin_registry(), root=root)
    assert not [f for f in findings if f.level == "error"], levels(findings)
    assert any("pull_request types cover" in m for _, m in levels(findings, "workflow"))
    assert any("subscribes to issue_comment" in m for _, m in levels(findings, "workflow"))
    assert any("policy is read from the base branch" in m for _, m in levels(findings, "workflow"))
    assert ("warn", "branch rules not checked: no GITHUB_TOKEN") in levels(findings, "repository")
    assert doctor.worst(findings) == 0


def test_a_sloppy_setup_gets_specific_fixes(tmp_path):
    root = repo_with(tmp_path, SLOPPY_WORKFLOW)
    findings = doctor.run(str(root / "mergeproof.yaml"), builtin_registry(), root=root)
    messages = "\n".join(f"{f.level} {f.message} | {f.fix}" for f in findings)
    assert "action ref 'main' is a branch" in messages
    assert "pull_request types miss edited, labeled, unlabeled" in messages
    assert "receipts are on but the workflow does not run on pull_request `closed`" in messages
    assert "does not run on issue_comment" in messages and "`types: [created, edited]`" in messages
    assert "does not run on check_suite" in messages
    assert "`statuses: write` is missing" in messages
    assert "checks: write covers reading other jobs' results" in messages
    assert "`checks: write` is no longer needed" in messages
    assert "`contents: write` is missing" in messages
    assert "checkout has no base-branch `ref`" in messages
    assert "MERGEPROOF_PR_NUMBER" not in messages, "only asked for when comment or check-suite events are subscribed"
    assert doctor.worst(findings) == 1
    text = doctor.render_text(findings)
    assert "[error] workflow:" in text and "        fix: " in text and "error(s)" in text
    assert json.loads(json.dumps(doctor.to_json(findings)))[0]["area"] == "policy"


def test_missing_pieces_are_reported_not_assumed(tmp_path):
    (tmp_path / "mergeproof.yaml").write_text("rules:\n  - id: r\n    require: [{ check: nope }]\n")
    findings = doctor.run(str(tmp_path / "mergeproof.yaml"), builtin_registry(), root=tmp_path)
    msgs = levels(findings)
    assert ("error", "rule 'r' / 'nope': unknown check 'nope'") in msgs
    assert any(level == "error" and "no workflow under" in m for level, m in msgs)
    broken = tmp_path / "broken.yaml"
    broken.write_text("rules: [")
    assert levels(doctor.run(str(broken), builtin_registry(), root=tmp_path), "policy")[0][0] == "error"


def test_verifiers_named_by_the_policy_must_exist(tmp_path):
    policy = textwrap.dedent(
        """
        rules:
          - id: traces
            when: { paths: ["src/**"] }
            require:
              - check: evidence.links
                name: known
                with: { verify: http }
              - check: evidence.links
                name: unknown
                with: { verify: nothing-provides-this }
        """
    )
    root = repo_with(tmp_path, GOOD_WORKFLOW, policy)
    findings = levels(doctor.run(str(root / "mergeproof.yaml"), builtin_registry(), root=root), "policy")
    assert ("ok", "verifier `http` (rule 'traces') is installed") in findings
    assert any(level == "error" and "`nothing-provides-this`, which is not installed" in m for level, m in findings)


def test_events_without_pr_number_and_default_permissions(tmp_path):
    workflow = textwrap.dedent(
        """
        on:
          pull_request:
          issue_comment:
        jobs:
          gate:
            runs-on: ubuntu-latest
            steps:
              - uses: Aryamanz29/mergeproof@1234567890abcdef1234567890abcdef12345678
        """
    )
    root = repo_with(tmp_path, workflow)
    msgs = levels(doctor.run(str(root / "mergeproof.yaml"), builtin_registry(), root=root), "workflow")
    assert any(level == "error" and "without MERGEPROOF_PR_NUMBER" in m for level, m in msgs)
    assert any(level == "warn" and "no `permissions:` block" in m for level, m in msgs)
    assert any(level == "ok" and "action pinned to 1234567" in m for level, m in msgs)


@respx.mock
def test_repository_rules_via_ruleset_then_protection(tmp_path):
    root = repo_with(tmp_path, GOOD_WORKFLOW)
    client = github.Client("tok")
    respx.get(f"{API}/repos/o/r").mock(return_value=httpx.Response(200, json={"default_branch": "main"}))
    rules = respx.get(f"{API}/repos/o/r/rules/branches/main")
    protection = respx.get(f"{API}/repos/o/r/branches/main/protection/required_status_checks")

    rules.mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "type": "required_status_checks",
                    "parameters": {"required_status_checks": [{"context": "mergeproof"}]},
                }
            ],
        )
    )
    findings = levels(
        doctor.run(str(root / "mergeproof.yaml"), builtin_registry(), root=root, repo="o/r", client=client),
        "repository",
    )
    assert findings == [("ok", "o/r: `mergeproof` status is required on main (ruleset)")]

    rules.mock(return_value=httpx.Response(200, json=[]))
    protection.mock(return_value=httpx.Response(200, json={"contexts": ["lint"]}))
    findings = levels(
        doctor.run(str(root / "mergeproof.yaml"), builtin_registry(), root=root, repo="o/r", client=client),
        "repository",
    )
    assert findings[0][0] == "error" and "branch protection requires lint" in findings[0][1]

    rules.mock(return_value=httpx.Response(404, json={}))
    protection.mock(return_value=httpx.Response(404, json={}))
    findings = levels(
        doctor.run(str(root / "mergeproof.yaml"), builtin_registry(), root=root, repo="o/r", client=client),
        "repository",
    )
    assert findings[0][0] == "warn" and "could not read the rules" in findings[0][1]

    findings = levels(
        doctor.run(str(root / "mergeproof.yaml"), builtin_registry(), root=root, repo=None, client=client), "repository"
    )
    assert findings == [("warn", "branch rules not checked: repository unknown")]


def test_receipt_companion_workflow_is_not_nagged_about_gate_events(tmp_path):
    root = repo_with(tmp_path, GOOD_WORKFLOW)
    (root / ".github" / "workflows" / "receipt.yml").write_text(
        textwrap.dedent(
            """
            on:
              pull_request:
                types: [closed]
            jobs:
              receipt:
                runs-on: ubuntu-latest
                permissions: { contents: write, pull-requests: write, checks: read }
                steps:
                  - uses: actions/checkout@v4
                  - uses: ./
                    with: { status: "false", review-comments: "false" }
            """
        )
    )
    findings = doctor.run(str(root / "mergeproof.yaml"), builtin_registry(), root=root)
    msgs = [m for level, m in levels(findings, "workflow")]
    receipt_msgs = [m for m in msgs if m.startswith(".github/workflows/receipt.yml")]
    assert any("receipt companion" in m for m in receipt_msgs)
    assert not any("pull_request types miss" in m or "check_suite" in m or "checkout" in m for m in receipt_msgs)
