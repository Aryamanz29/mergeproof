import io
import json
import subprocess
import sys

import pytest

from mergeproof.cli import main

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
    assert "requirements are satisfied" in capsys.readouterr().out


def test_plumbing_round_trip(repo, capsys, monkeypatch):
    policy = repo / "mergeproof.yaml"
    assert run("context", "--local", "--base", "main", "--root", repo) == 0
    context_json = capsys.readouterr().out
    (repo / "ctx.json").write_text(context_json)
    assert run("check", "--context", repo / "ctx.json", "-p", policy, "-f", "json") == 1
    (repo / "report.json").write_text(capsys.readouterr().out)
    assert run("report", repo / "report.json", "-f", "md") == 0
    assert "need attention" in capsys.readouterr().out
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
    monkeypatch.setattr(github, "create_check_run", lambda *a: calls.append("check") or "https://k/1")
    assert run("comment", path, "--status", "--check-run") == 0
    assert calls == ["comment", "check", "status"]
    err = capsys.readouterr().err
    assert "comment https://c/1" in err and "check run https://k/1" in err and "status success" in err


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
    monkeypatch.setattr(github, "create_check_run", lambda *a: calls.append("check") or "https://k/1")
    assert run("check", "--context", context, "-p", policy, "-q", "--status") == 0
    assert calls == ["status"]
    calls.clear()
    assert run("check", "--context", context, "-p", policy, "-q", "--comment", "--check-run") == 0
    assert calls == [("comment", True), "check"]
    assert run("check", "--context", context, "-p", policy, "-q") == 0
    assert calls == [("comment", True), "check"]
