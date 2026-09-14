import io
import json
import subprocess
import sys

import pytest

from mergeproof.cli import main
from mergeproof.providers import github

POLICY = """\
rules:
  - id: src
    when: { paths: ["src/**"] }
    require:
      - check: tests.changed
        with: { any_of: ["tests/**"] }
      - check: evidence.field
        with: { key: environment, equals: staging }
"""


def sh(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    sh(tmp_path, "init", "-q", "-b", "main")
    sh(tmp_path, "config", "user.email", "t@example.com")
    sh(tmp_path, "config", "user.name", "t")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    sh(tmp_path, "add", ".")
    sh(tmp_path, "commit", "-qm", "init")
    sh(tmp_path, "checkout", "-qb", "feature")
    (tmp_path / "src" / "a.py").write_text("x = 2\n")
    sh(tmp_path, "commit", "-qam", "fix: bump")
    (tmp_path / "mergeproof.yaml").write_text(POLICY)
    return tmp_path


def run(*argv):
    with pytest.raises(SystemExit) as exc:
        main([str(a) for a in argv])
    return exc.value.code


def test_check_exit_codes_and_outputs(repo, capsys):
    policy = repo / "mergeproof.yaml"
    code = run("check", "--local", "--base", "main", "--root", repo, "-p", policy, "-o", repo / "r.json")
    assert code == 1
    out = capsys.readouterr().out
    assert out.startswith("mergeproof: FAIL") and "```evidence" in out
    report = json.loads((repo / "r.json").read_text())
    assert report["source"] == "local" and report["rules"][0]["files"] == ["src/a.py"]

    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test(): pass\n")
    (repo / "body.md").write_text("```evidence\nenvironment: staging\n```\n")
    code = run(
        "check", "--local", "--base", "main", "--root", repo, "-p", policy, "--body-file", repo / "body.md", "-f", "md"
    )
    assert code == 0
    assert "requirements satisfied" in capsys.readouterr().out


def test_plumbing_round_trip(repo, capsys, monkeypatch):
    policy = repo / "mergeproof.yaml"
    assert run("context", "--local", "--base", "main", "--root", repo) == 0
    context_json = capsys.readouterr().out
    (repo / "ctx.json").write_text(context_json)
    assert run("check", "--context", repo / "ctx.json", "-p", policy, "-f", "json") == 1
    (repo / "report.json").write_text(capsys.readouterr().out)
    assert run("report", repo / "report.json", "-f", "md") == 0
    assert "To merge:" in capsys.readouterr().out
    assert run("report", repo / "report.json", "--exit-status") == 1
    capsys.readouterr()
    assert run("report", repo / "report.json", "-f", "junit") == 0
    assert capsys.readouterr().out.startswith("<?xml")
    assert run("report", repo / "report.json", "-f", "rdjson") == 0
    assert '"source"' in capsys.readouterr().out
    monkeypatch.setattr(sys, "stdin", io.StringIO((repo / "report.json").read_text()))
    assert run("report", "-", "-f", "text") == 0
    assert "FAIL" in capsys.readouterr().out


def test_explain_template_and_helpers(repo, capsys, tmp_path):
    policy = repo / "mergeproof.yaml"
    assert run("explain", "--local", "--base", "main", "--root", repo, "-p", policy) == 0
    assert "What this change must prove" in capsys.readouterr().out
    assert run("explain", "--local", "--base", "main", "--root", repo, "-p", policy, "-f", "text") == 0
    capsys.readouterr()
    assert run("template", "--local", "--base", "main", "--root", repo, "-p", policy) == 0
    assert "environment: staging" in capsys.readouterr().out
    assert run("validate", "-p", policy) == 0
    fresh = tmp_path / "new.yaml"
    assert run("init", "-p", fresh) == 0
    assert run("init", "-p", fresh) == 3
    assert run("validate", "-p", fresh) == 0
    assert run("agent-prompt", "-p", fresh) == 0
    assert "Evidence requirements" in capsys.readouterr().out
    assert run("checks") == 0
    listing = capsys.readouterr().out
    assert "review.human_verified  (GitHub mode only)" in listing
    assert "tests.changed\n" in listing and "PydanticUndefined" not in listing


def test_workflow_commands_ride_with_text_output_only(repo, capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    policy = repo / "mergeproof.yaml"
    assert run("check", "--local", "--base", "main", "--root", repo, "-p", policy) == 1
    assert "::error title=mergeproof::" in capsys.readouterr().out
    assert run("check", "--local", "--base", "main", "--root", repo, "-p", policy, "-f", "json") == 1
    json.loads(capsys.readouterr().out)
    assert run("check", "--local", "--base", "main", "--root", repo, "-p", policy, "-q") == 1
    assert capsys.readouterr().out == ""


def test_usage_errors_exit_3(repo, capsys, tmp_path, tmp_path_factory):
    assert run("validate", "-p", tmp_path / "missing.yaml") == 3
    bad = tmp_path / "bad.yaml"
    bad.write_text("rules:\n  - id: a\n    require: [{check: nope}]\n")
    assert run("validate", "-p", bad) == 3
    assert "unknown check" in capsys.readouterr().err
    empty = tmp_path_factory.mktemp("not-a-repo")
    assert run("check", "--local", "--base", "main", "--root", empty, "-p", repo / "mergeproof.yaml") == 3
    (tmp_path / "ctx.json").write_text("{not json")
    assert run("check", "--context", tmp_path / "ctx.json", "-p", repo / "mergeproof.yaml") == 3
    assert run("report", tmp_path / "absent.json") == 3


def test_comment_without_github_context_is_skipped(repo, capsys):
    policy = repo / "mergeproof.yaml"
    code = run("check", "--local", "--base", "main", "--root", repo, "-p", policy, "--comment", "-q")
    assert code == 1
    assert "needs a GitHub context" in capsys.readouterr().err


def test_command_surface_is_the_documented_one(capsys):
    from mergeproof.cli import build_parser

    commands = set(build_parser()._subparsers._group_actions[0].choices)
    assert commands == {
        "check",
        "explain",
        "template",
        "context",
        "report",
        "comment",
        "validate",
        "init",
        "checks",
        "agent-prompt",
        "receipt",
        "replay",
        "doctor",
    }
    assert "mcp" not in commands


def test_module_entry_point():
    proc = subprocess.run([sys.executable, "-m", "mergeproof", "--version"], capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stdout.startswith("mergeproof ")


def test_publish_calls_each_channel(tmp_path, monkeypatch, capsys):
    from mergeproof.policy import Severity
    from mergeproof.providers import github
    from mergeproof.report import Outcome, Report, RequirementResult, RuleResult, Status

    report = Report(
        source="github",
        repo="o/r",
        number=3,
        head_sha="a" * 40,
        rules=[
            RuleResult(
                id="r",
                severity=Severity.BLOCK,
                matched=True,
                requirements=[
                    RequirementResult(
                        label="x",
                        check="pr.body",
                        severity=Severity.BLOCK,
                        outcome=Outcome(status=Status.PASS, summary="ok"),
                    )
                ],
            )
        ],
    )
    path = tmp_path / "report.json"
    path.write_text(report.to_json())
    calls = []
    monkeypatch.setattr(github, "client_from_env", lambda: object())
    monkeypatch.setattr(github, "upsert_comment", lambda *a, **k: calls.append("comment") or "https://c/1")
    monkeypatch.setattr(github, "set_commit_status", lambda *a: calls.append("status"))
    assert run("comment", path, "--status") == 0
    assert calls == ["comment", "status"]
    err = capsys.readouterr().err
    assert "comment at https://c/1" in err and "commit status success" in err


def test_check_publishes_each_requested_channel(tmp_path, monkeypatch, capsys):
    from mergeproof.providers import github

    context = tmp_path / "ctx.json"
    context.write_text(
        json.dumps(
            {
                "source": "github",
                "online": True,
                "repo": "o/r",
                "number": 3,
                "head_sha": "a" * 40,
                "title": "docs",
                "files": [{"path": "README.md", "status": "modified"}],
            }
        )
    )
    policy = tmp_path / "mergeproof.yaml"
    policy.write_text("rules:\n  - id: r\n    require: [{check: pr.labels, with: {none_of: [wip]}}]\n")
    calls = []
    monkeypatch.setattr(github, "client_from_env", lambda: object())
    monkeypatch.setattr(
        github, "upsert_comment", lambda *a, **k: calls.append(("comment", k["create"])) or "https://c/1"
    )
    monkeypatch.setattr(github, "set_commit_status", lambda *a: calls.append("status"))
    monkeypatch.setattr(github, "sync_review_comments", lambda *a: calls.append("review") or {"created": 1})
    assert run("check", "--context", context, "-p", policy, "-q", "--status") == 0
    assert calls == ["status"]
    calls.clear()
    assert run("check", "--context", context, "-p", policy, "-q", "--review-comments") == 0
    assert calls == ["review"]
    calls.clear()
    assert run("check", "--context", context, "-p", policy, "-q", "--comment") == 0
    assert calls == [("comment", True)]
    assert run("check", "--context", context, "-p", policy, "-q") == 0
    assert calls == [("comment", True)]


def test_check_run_flag_is_refused(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["comment", "-", "--check-run"])
    assert exc.value.code == 3
    assert "removed in 0.8" in capsys.readouterr().err


def test_publish_writes_the_receipt_only_for_a_merged_pr(tmp_path, monkeypatch, capsys):
    from mergeproof import receipt
    from mergeproof.report import Report

    report = Report(source="github", repo="o/r", number=7, head_sha="a" * 40, base_ref="main")
    path = tmp_path / "report.json"
    calls = []
    monkeypatch.setattr(github, "client_from_env", lambda: object())
    monkeypatch.setattr(github, "upsert_comment", lambda *a, **k: calls.append(("comment", a[3])) or "https://c/1")
    monkeypatch.setattr(receipt, "write", lambda *a: calls.append("receipt") or "https://r/1")

    path.write_text(report.to_json())
    assert run("comment", path, "--receipt") == 0
    assert [c for c in calls if c == "receipt"] == [], "an open PR gets no receipt"

    calls.clear()
    report.merged, report.merge_commit_sha, report.merged_by = True, "c" * 40, "lead"
    path.write_text(report.to_json())
    assert run("comment", path, "--receipt") == 0
    assert calls[0] == "receipt" and "[receipt](https://r/1)" in calls[1][1]
    assert "receipt at https://r/1" in capsys.readouterr().err


def test_publish_survives_a_receipt_permission_error(tmp_path, monkeypatch, capsys):
    import httpx

    from mergeproof import receipt
    from mergeproof.report import Report

    report = Report(source="github", repo="o/r", number=7, head_sha="a" * 40, merged=True, merge_commit_sha="c" * 40)
    path = tmp_path / "report.json"
    path.write_text(report.to_json())
    calls = []
    monkeypatch.setattr(github, "client_from_env", lambda: object())
    monkeypatch.setattr(github, "upsert_comment", lambda *a, **k: calls.append("comment") or "https://c/1")

    def forbidden(*a):
        request = httpx.Request("POST", "https://api.github.com/x")
        raise httpx.HTTPStatusError("403", request=request, response=httpx.Response(403, request=request))

    monkeypatch.setattr(receipt, "write", forbidden)
    assert run("comment", path, "--receipt") == 0
    assert calls == ["comment"]
    assert "contents: write" in capsys.readouterr().err


def test_receipt_command_prints_a_summary(monkeypatch, capsys):
    from mergeproof import receipt
    from mergeproof.report import Report

    report = Report(source="github", repo="o/r", number=7, head_sha="a" * 40, merged=True, merge_commit_sha="c" * 40)
    monkeypatch.setattr(github, "client_from_env", lambda: object())
    monkeypatch.setattr(receipt, "read", lambda client, repo, key, branch: receipt.build(report))
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    assert run("receipt", "#7") == 0
    assert "#7 merged as ccccccc" in capsys.readouterr().out
    assert run("receipt", "#7", "--json") == 0
    assert json.loads(capsys.readouterr().out)["receipt"]["pull_request"] == 7
    monkeypatch.setattr(receipt, "read", lambda *a: (_ for _ in ()).throw(LookupError("no receipt for ccccccc")))
    assert run("receipt", "#7") == 1
    assert "no receipt" in capsys.readouterr().err


def test_replay_command_runs_read_only(tmp_path, monkeypatch, capsys):
    import base64

    from mergeproof import replay
    from mergeproof.context import ChangedFile, Context

    (tmp_path / "candidate.yaml").write_text(POLICY)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(github, "client_from_env", lambda: object())

    never = "rules:\n  - id: never\n    when: { paths: ['never/**'] }\n    require: [{ check: files.changed }]\n"

    class Client:
        def get(self, path, **params):
            if path == "/repos/o/r":
                return {"default_branch": "main"}
            if path.endswith("/contents/mergeproof.yaml"):
                return {"content": base64.b64encode(never.encode()).decode()}
            raise AssertionError(path)

    monkeypatch.setattr(github, "client_from_env", lambda: Client())
    monkeypatch.setattr(
        replay,
        "merged_pulls",
        lambda client, repo, last, since: [{"number": 9, "title": "t", "merged_at": "2026-09-09T00:00:00Z"}],
    )
    ctx = Context(
        source="github", online=True, repo="o/r", number=9, head_sha="a" * 40, files=[ChangedFile(path="src/a.py")]
    )
    monkeypatch.setattr(replay, "fetch", lambda client, repo, number: ctx)

    code = run("replay", "-p", tmp_path / "candidate.yaml", "--against", "current", "--save", tmp_path / "s", "-q")
    out, err = capsys.readouterr()
    assert code == 0 and "#9  2026-09-09  fail" in out and "(was pass)" in out
    assert "1 scenario files" in err and (tmp_path / "s" / "pr-9.json").exists()
    assert run("replay", "-p", tmp_path / "candidate.yaml", "--fail-on-block", "-q", "-f", "json") == 1
    assert json.loads(capsys.readouterr().out)[0]["verdict"] == "fail"

    monkeypatch.delenv("GITHUB_REPOSITORY")
    assert run("replay", "-p", tmp_path / "candidate.yaml") == 3


def test_validate_lists_rule_sources_for_inherited_policies(tmp_path, capsys):
    (tmp_path / "base.yaml").write_text(
        "rules:\n  - id: inherited\n    when: { paths: ['src/**'] }\n    require: [{ check: files.changed }]\n"
    )
    (tmp_path / "mergeproof.yaml").write_text(
        "extends: path:base.yaml\nrules:\n  - id: local\n    when: { labels: ['x'] }\n"
        "    require: [{ check: pr.labels, with: { any_of: ['x'] } }]\n"
    )
    assert run("validate", "-p", tmp_path / "mergeproof.yaml") == 0
    out = capsys.readouterr().out
    assert "inherited  path:base.yaml" in out and "local      this file" in out


SHELLY = """\
rules:
  - id: src
    when: { paths: ["src/**"] }
    require:
      - check: tests.changed
        with: { any_of: ["tests/**"] }
      - check: shell
        name: lint passes
        with: { run: "make lint" }
  - id: docs
    when: { paths: ["docs/**"] }
    require:
      - check: files.changed
        with: { any_of: ["docs/**"] }
"""


def test_validate_notes_shell_requirements(tmp_path, capsys):
    (tmp_path / "p.yaml").write_text(SHELLY)
    assert run("validate", "-p", tmp_path / "p.yaml") == 0
    out = capsys.readouterr().out
    assert "note: rule 'src' / 'lint passes' runs a shell command" in out
    (tmp_path / "clean.yaml").write_text(POLICY)
    assert run("validate", "-p", tmp_path / "clean.yaml") == 0
    assert "note:" not in capsys.readouterr().out


def test_checks_usage_counts_checks_and_lists_shell_commands(tmp_path, capsys):
    (tmp_path / "p.yaml").write_text(SHELLY)
    assert run("checks", "--usage", "-p", tmp_path / "p.yaml") == 0
    out = capsys.readouterr().out
    assert "2 rule(s), 3 requirement(s)" in out
    assert out.index("files.changed") < out.index("tests.changed"), "ties sort by name"
    assert "shell commands:\n  src / lint passes: make lint" in out
    assert run("checks") == 0
    listing = capsys.readouterr().out
    assert "tests.changed" in listing and "shell commands" not in listing


def test_doctor_command_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "gate.yml").write_text(
        "on:\n  pull_request:\n    types: [opened, synchronize, reopened, edited, labeled, unlabeled, closed]\n"
        "jobs:\n  gate:\n    runs-on: ubuntu-latest\n"
        "    permissions: { contents: write, pull-requests: write, statuses: write, checks: read }\n"
        "    steps:\n      - uses: actions/checkout@v4\n        with: { ref: main }\n"
        "      - uses: Aryamanz29/mergeproof@v0\n"
    )
    (tmp_path / "mergeproof.yaml").write_text(
        "rules:\n  - id: r\n    when: { paths: ['src/**'] }\n    require: [{ check: files.changed }]\n"
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert run("doctor", "-p", tmp_path / "mergeproof.yaml", "--root", tmp_path) == 0
    out = capsys.readouterr().out
    assert "[   ok] workflow" in out and "no GITHUB_TOKEN" in out
    (tmp_path / ".github" / "workflows" / "gate.yml").write_text("on: [push]\njobs: {}\n")
    assert run("doctor", "-p", tmp_path / "mergeproof.yaml", "--root", tmp_path, "-f", "json") == 1
    data = json.loads(capsys.readouterr().out)
    assert any(f["level"] == "error" and "no workflow under" in f["message"] for f in data)
