import json
import subprocess
import sys

import pytest

from mergeproof.cli import main


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    git(tmp_path, "checkout", "-qb", "feature")
    (tmp_path / "src" / "a.py").write_text("x = 2\n")
    git(tmp_path, "commit", "-qam", "fix: bump")
    (tmp_path / "src" / "b.py").write_text("y = 1\n")  # untracked, still counts
    (tmp_path / "mergeproof.yaml").write_text(
        "rules:\n  - id: r\n    when: {paths: ['src/**']}\n    require:\n"
        "      - check: tests.changed\n        with: {any_of: ['tests/**']}\n"
        "      - check: evidence.field\n        with: {key: tenant, equals: staging}\n"
    )
    return tmp_path


def run_cli(*args):
    with pytest.raises(SystemExit) as e:
        main(list(args))
    return e.value.code


def test_check_local_fails_then_passes(repo, capsys):
    code = run_cli(
        "check",
        "--local",
        "--base",
        "main",
        "--root",
        str(repo),
        "--policy",
        str(repo / "mergeproof.yaml"),
        "--json",
        str(repo / "out.json"),
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "evidence missing" in out and "```evidence" in out
    data = json.loads((repo / "out.json").read_text())
    assert data["mode"] == "local"
    files = data["rules"][0]["matched_files"]
    assert "src/a.py" in files and "src/b.py" in files

    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test(): pass\n")
    (repo / "body.md").write_text("```evidence\ntenant: staging\n```\n")
    code = run_cli(
        "check",
        "--local",
        "--base",
        "main",
        "--root",
        str(repo),
        "--policy",
        str(repo / "mergeproof.yaml"),
        "--body-file",
        str(repo / "body.md"),
        "-q",
    )
    assert code == 0


def test_explain_validate_init_checks(repo, capsys, tmp_path):
    assert (
        run_cli("explain", "--local", "--base", "main", "--root", str(repo), "--policy", str(repo / "mergeproof.yaml"))
        == 0
    )
    assert "what this change must prove" in capsys.readouterr().out
    assert run_cli("validate", "--policy", str(repo / "mergeproof.yaml")) == 0
    target = tmp_path / "new.yaml"
    assert run_cli("init", "--policy", str(target)) == 0
    assert run_cli("validate", "--policy", str(target)) == 0
    assert run_cli("agent-prompt", "--policy", str(target)) == 0
    assert "Evidence requirements" in capsys.readouterr().out
    assert run_cli("checks") == 0
    assert "review.human_verified" in capsys.readouterr().out


def test_module_entrypoint():
    r = subprocess.run([sys.executable, "-m", "mergeproof.cli", "--version"], capture_output=True, text=True)
    assert r.returncode == 0 and "mergeproof" in r.stdout
