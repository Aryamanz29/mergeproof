import json
import subprocess

import httpx
import pytest
import respx

from mergeproof.context import Context, ContextError
from mergeproof.providers import git, github
from mergeproof.report import Annotation, Status


def sh(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    sh(tmp_path, "init", "-q", "-b", "main")
    sh(tmp_path, "config", "user.email", "t@example.com")
    sh(tmp_path, "config", "user.name", "Tester")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "old.txt").write_text("old\n")
    sh(tmp_path, "add", ".")
    sh(tmp_path, "commit", "-qm", "init")
    sh(tmp_path, "checkout", "-qb", "feature")
    (tmp_path / "src" / "a.py").write_text("x = 2\n")
    sh(tmp_path, "mv", "old.txt", "new.txt")
    sh(tmp_path, "commit", "-qam", "fix: bump")
    (tmp_path / "untracked.py").write_text("y = 1\n")
    return tmp_path


def test_from_git_sees_committed_renamed_and_untracked(repo):
    ctx = git.from_git(base="main", root=str(repo))
    by_path = {f.path: f for f in ctx.files}
    assert by_path["src/a.py"].status == "modified"
    assert by_path["new.txt"].status == "renamed" and by_path["new.txt"].previous_path == "old.txt"
    assert by_path["untracked.py"].status == "added"
    assert (
        ctx.tree is not None and {"src/a.py", "new.txt", "untracked.py"} <= set(ctx.tree) and "old.txt" not in ctx.tree
    )
    assert ctx.title == "fix: bump" and ctx.author == "Tester" and ctx.base_ref == "main"
    assert ctx.source == "local" and not ctx.online and len(ctx.head_sha) == 40


def test_from_git_errors_are_clean(tmp_path):
    with pytest.raises(ContextError, match="git merge-base"):
        git.from_git(base="main", root=str(tmp_path))


def test_parse_name_status_handles_every_code():
    files = git.parse_name_status("A\tadded.py\nM\tmod.py\nD\tgone.py\nR100\told\tnew\nT\ttype.py\n\n")
    assert [(f.path, f.status) for f in files] == [
        ("added.py", "added"),
        ("mod.py", "modified"),
        ("gone.py", "removed"),
        ("new", "renamed"),
        ("type.py", "modified"),
    ]


def test_hydrate_from_gh_without_gh_is_a_noop(repo, monkeypatch):
    monkeypatch.setattr(git.shutil, "which", lambda name: None)
    ctx = git.from_git(base="main", root=str(repo))
    assert git.hydrate_from_gh(ctx) is ctx


PR = {
    "title": "fix: thing",
    "body": "```evidence\nenvironment: staging\n```",
    "user": {"login": "octocat"},
    "labels": [{"name": "bug"}],
    "base": {"ref": "main", "sha": "b" * 40},
    "head": {"sha": "a" * 40},
}


@respx.mock
def test_fetch_builds_a_full_context():
    api = "https://api.github.com"
    respx.get(f"{api}/repos/o/r/pulls/7").mock(return_value=httpx.Response(200, json=PR))
    respx.get(f"{api}/repos/o/r/pulls/7/files").mock(
        return_value=httpx.Response(200, json=[{"filename": "src/a.py", "status": "modified"}])
    )
    respx.get(f"{api}/repos/o/r/issues/7/comments").mock(
        return_value=httpx.Response(
            200, json=[{"user": {"login": "lead"}, "body": "/verified aaaaaaa", "created_at": "t", "html_url": "u"}]
        )
    )
    respx.get(f"{api}/repos/o/r/pulls/7/reviews").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"user": {"login": "lead"}, "body": "", "state": "APPROVED", "submitted_at": "t", "commit_id": "a" * 40}
            ],
        )
    )
    respx.get(f"{api}/repos/o/r/pulls/7/comments").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{api}/repos/o/r/git/trees/{'a' * 40}").mock(
        return_value=httpx.Response(
            200,
            json={
                "truncated": False,
                "tree": [
                    {"path": "src/a.py", "type": "blob"},
                    {"path": "src", "type": "tree"},
                    {"path": "tests/test_a.py", "type": "blob"},
                ],
            },
        )
    )
    respx.get(f"{api}/repos/o/r/commits/{'a' * 40}/check-runs").mock(
        return_value=httpx.Response(
            200,
            json={
                "check_runs": [
                    {
                        "name": "unit",
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-01-01T00:00:00Z",
                    }
                ]
            },
        )
    )
    ctx = github.fetch(github.Client("tok"), "o/r", 7)
    assert ctx.online and ctx.source == "github" and ctx.repo == "o/r" and ctx.number == 7
    assert ctx.labels == ["bug"] and ctx.head_short == "aaaaaaa"
    assert [c.kind for c in ctx.comments] == ["comment", "review"]
    assert ctx.comments[1].state == "APPROVED" and ctx.comments[1].commit == "a" * 40
    assert ctx.check_runs[0].conclusion == "success" and ctx.check_runs[0].started_at == "2026-01-01T00:00:00Z"
    assert ctx.tree == ["src/a.py", "tests/test_a.py"]
    assert ctx.evidence().get("environment") == "staging"
    assert Context.from_json(ctx.to_json()) == ctx


@respx.mock
def test_paginate_walks_pages():
    api = "https://api.github.com"
    route = respx.get(f"{api}/repos/o/r/pulls/1/files")
    route.side_effect = [
        httpx.Response(200, json=[{"filename": f"f{i}.py", "status": "added"} for i in range(100)]),
        httpx.Response(200, json=[{"filename": "last.py", "status": "added"}]),
    ]
    items = github.Client("tok").paginate("/repos/o/r/pulls/1/files")
    assert len(items) == 101 and route.call_count == 2


@respx.mock
def test_upsert_comment_updates_existing_marker_or_creates():
    api = "https://api.github.com"
    respx.get(f"{api}/repos/o/r/issues/7/comments").mock(
        return_value=httpx.Response(200, json=[{"id": 5, "body": "<!-- m --> old", "html_url": "https://c/5"}])
    )
    patch = respx.patch(f"{api}/repos/o/r/issues/comments/5").mock(return_value=httpx.Response(200, json={}))
    assert github.upsert_comment(github.Client("tok"), "o/r", 7, "new", "<!-- m -->") == "https://c/5"
    assert json.loads(patch.calls[0].request.content) == {"body": "new"}

    respx.get(f"{api}/repos/o/r/issues/8/comments").mock(return_value=httpx.Response(200, json=[]))
    post = respx.post(f"{api}/repos/o/r/issues/8/comments").mock(
        return_value=httpx.Response(201, json={"html_url": "https://c/9"})
    )
    assert github.upsert_comment(github.Client("tok"), "o/r", 8, "new", "<!-- m -->") == "https://c/9"
    assert post.called
    assert github.upsert_comment(github.Client("tok"), "o/r", 8, "new", "<!-- m -->", create=False) == ""
    assert post.call_count == 1


def test_locate_pr_from_event_and_env(tmp_path, monkeypatch):
    for var in ("MERGEPROOF_REPO", "MERGEPROOF_PR_NUMBER", "GITHUB_EVENT_PATH", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ContextError):
        github.locate_pr()
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 12}, "repository": {"full_name": "o/r"}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert github.locate_pr() == ("o/r", 12)
    monkeypatch.setenv("MERGEPROOF_PR_NUMBER", "99")
    monkeypatch.setenv("MERGEPROOF_REPO", "x/y")
    assert github.locate_pr() == ("x/y", 99)


def test_client_from_env_requires_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(ContextError, match="GITHUB_TOKEN"):
        github.client_from_env()


def test_step_summary_and_output_files(tmp_path, monkeypatch):
    summary, output = tmp_path / "s.md", tmp_path / "o.txt"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    github.write_step_summary("# hi")
    github.write_output("verdict", "pass")
    assert summary.read_text() == "# hi\n" and output.read_text() == "verdict=pass\n"


@respx.mock
def test_commit_status_and_check_run_payloads():
    api = "https://api.github.com"
    status = respx.post(f"{api}/repos/o/r/statuses/abc").mock(return_value=httpx.Response(201, json={}))
    check = respx.post(f"{api}/repos/o/r/check-runs").mock(
        return_value=httpx.Response(201, json={"html_url": "https://c/1"})
    )
    client = github.Client("tok")
    github.set_commit_status(client, "o/r", "abc", Status.PENDING, "x" * 200, "https://run")
    sent = json.loads(status.calls[0].request.content)
    assert sent["state"] == "pending" and sent["context"] == "mergeproof"
    assert sent["description"] == "x" * 140  # the status API rejects emoji; the mark lives on the Check Run
    assert sent["target_url"] == "https://run"

    notes = [Annotation(path="src/a.py", message="expected a test")]
    url = github.create_check_run(client, "o/r", "abc", Status.FAIL, "0 of 1", "## summary", notes, "https://run")
    assert url == "https://c/1"
    sent = json.loads(check.calls[0].request.content)
    assert sent["conclusion"] == "failure" and sent["name"] == "mergeproof" and sent["details_url"] == "https://run"
    assert sent["output"]["title"] == "🛡️ 0 of 1"
    note = sent["output"]["annotations"][0]
    assert note == {
        "path": "src/a.py",
        "start_line": 1,
        "end_line": 1,
        "annotation_level": "failure",
        "message": "expected a test",
    }
    for verdict, conclusion in (
        (Status.PASS, "success"),
        (Status.WARN, "neutral"),
        (Status.PENDING, "action_required"),
    ):
        assert github.CHECK_CONCLUSION[verdict] == conclusion


def test_run_url(monkeypatch):
    for var in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        monkeypatch.delenv(var, raising=False)
    assert github.run_url() is None
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_RUN_ID", "9")
    assert github.run_url() == "https://github.com/o/r/actions/runs/9"


def review_report():
    from mergeproof import engine, policy
    from mergeproof.checks.registry import builtin_registry

    from .conftest import make_context

    pol = policy.loads(
        "rules:\n"
        "  - id: tests\n    when: {paths: ['src/**']}\n    instructions: Add a regression test.\n"
        "    require: [{check: tests.changed, with: {map: {'src/{name}.py': 'tests/test_{name}.py'}}}]\n"
        "  - id: evidence\n    when: {paths: ['src/**']}\n"
        "    require:\n      - {check: evidence.field, name: environment, with: {key: environment}}\n"
        "      - {check: ci.job_passed, name: ci, with: {name: unit}}\n"
    )
    report = engine.evaluate(
        pol, make_context(files=["src/a.py", "src/b.py"], repo="o/r", number=5), builtin_registry()
    )
    return report


def test_review_comment_bodies_pick_files_and_skip_unactionable_pending():
    bodies = github.review_comment_bodies(review_report())
    keys = sorted(bodies)
    assert keys == [
        ("src/a.py", "evidence:environment"),
        ("src/a.py", "tests:tests.changed:src/a.py"),
        ("src/b.py", "tests:tests.changed:src/b.py"),
    ]
    body = bodies[("src/a.py", "tests:tests.changed:src/a.py")]
    assert body.startswith("<!-- mergeproof-review:tests:tests.changed:src/a.py -->")
    assert "**mergeproof · tests.changed** <sub>rule `tests`, blocking</sub>" in body
    assert "expected a changed test matching tests/test_a.py" in body and "Add a regression test." in body
    assert "touches `src/a.py`, `src/b.py`" in bodies[("src/a.py", "evidence:environment")]


@respx.mock
def test_sync_review_comments_creates_updates_and_deletes():
    api = "https://api.github.com"
    report = review_report()
    bodies = github.review_comment_bodies(report)
    existing_key = "tests:tests.changed:src/a.py"
    stale_key = "gone:old:src/z.py"
    respx.get(f"{api}/repos/o/r/pulls/5/comments").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "body": f"<!-- mergeproof-review:{existing_key} -->\nold text"},
                {"id": 2, "body": f"<!-- mergeproof-review:{stale_key} -->\nstale"},
                {"id": 3, "body": "a human comment"},
            ],
        )
    )
    created = respx.post(f"{api}/repos/o/r/pulls/5/comments").mock(return_value=httpx.Response(201, json={}))
    updated = respx.patch(f"{api}/repos/o/r/pulls/comments/1").mock(return_value=httpx.Response(200, json={}))
    deleted = respx.delete(f"{api}/repos/o/r/pulls/comments/2").mock(return_value=httpx.Response(204))
    counts = github.sync_review_comments(github.Client("t"), report, bodies)
    assert counts == {"created": 2, "updated": 1, "deleted": 1}
    sent = json.loads(created.calls[0].request.content)
    assert (
        sent["subject_type"] == "file"
        and sent["commit_id"] == report.head_sha
        and sent["path"] in {"src/a.py", "src/b.py"}
    )
    assert updated.called and deleted.called
