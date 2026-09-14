import json

import httpx
import respx

from mergeproof import policy, replay
from mergeproof.checks.registry import builtin_registry
from mergeproof.context import ChangedFile, Context
from mergeproof.providers import github
from mergeproof.report import Status

API = "https://api.github.com"
CANDIDATE = policy.loads(
    "rules:\n"
    "  - id: src-needs-tests\n"
    "    when: { paths: ['src/**'] }\n"
    "    require:\n"
    "      - check: tests.changed\n"
    "        with: { any_of: ['tests/**'] }\n"
)
NEVER = "rules:\n  - id: never\n    when: { paths: ['never/**'] }\n    require: [{ check: files.changed }]\n"
LENIENT = policy.loads(NEVER)


def pull(number, merged_at, title="x"):
    return {"number": number, "title": title, "merged_at": merged_at, "user": {"login": "dev"}}


@respx.mock
def test_merged_pulls_filters_sorts_and_bounds():
    client = github.Client("tok")
    page = [
        pull(3, "2026-09-03T00:00:00Z"),
        pull(2, None),
        pull(1, "2026-09-01T00:00:00Z"),
        pull(4, "2026-09-04T00:00:00Z"),
    ]
    respx.get(f"{API}/repos/o/r/pulls").mock(return_value=httpx.Response(200, json=page))
    found = replay.merged_pulls(client, "o/r", last=2)
    assert [p["number"] for p in found] == [4, 3]
    assert [p["number"] for p in replay.merged_pulls(client, "o/r", since="2026-09-03")] == [4, 3]
    assert replay.merged_pulls(client, "o/r", last=10)[-1]["merged_by"] == "dev"


def fake_fetcher(files_by_number):
    def fetcher(client, repo, number):
        if number not in files_by_number:
            raise RuntimeError("gone")
        return Context(
            source="github",
            online=True,
            repo=repo,
            number=number,
            head_sha="a" * 40,
            files=[ChangedFile(path=p) for p in files_by_number[number]],
        )

    return fetcher


def test_replay_reports_verdicts_blockers_and_changes(tmp_path):
    pulls = [
        pull(3, "2026-09-03T00:00:00Z", "fix: three"),
        pull(2, "2026-09-02T00:00:00Z", "docs"),
        pull(1, "2026-09-01T00:00:00Z"),
    ]
    fetcher = fake_fetcher({3: ["src/a.py"], 2: ["README.md"]})
    seen = []
    result = replay.replay(
        object(), "o/r", pulls, CANDIDATE, builtin_registry(), against=LENIENT, fetcher=fetcher, progress=seen.append
    )
    assert seen == ["#3 fix: three", "#2 docs", "#1 x"]
    by_number = {r.number: r for r in result.rows}
    assert by_number[3].verdict == Status.FAIL and by_number[3].blocking == ["src-needs-tests · tests.changed"]
    assert by_number[3].changed and by_number[2].verdict == Status.PASS and not by_number[2].changed
    assert by_number[1].error == "RuntimeError: gone"
    assert [r.number for r in result.would_block] == [3] and [r.number for r in result.applied] == [3]

    text = replay.render_text(result, "o/r")
    assert "#3  2026-09-03  fail     fix: three  (was pass)" in text
    assert "needs  src-needs-tests · tests.changed" in text and "#1  2026-09-01  error" in text
    assert "3 merged pull requests in o/r; the policy applied to 1 and would have blocked 1" in text
    assert "1 of them not blocked by the policy compared against" in text
    assert "most common blockers:\n    1  src-needs-tests · tests.changed" in text

    data = json.loads(replay.render_json(result))
    assert data[0] == {
        "number": 3,
        "title": "fix: three",
        "merged_at": "2026-09-03T00:00:00Z",
        "verdict": "fail",
        "against": "pass",
        "blocking": ["src-needs-tests · tests.changed"],
        "error": None,
    }
    assert data[2]["verdict"] == "error"

    written = replay.save_scenarios(result, tmp_path / "scenarios")
    assert [p.name for p in written] == ["pr-3.json", "pr-2.json"]
    saved = json.loads(written[0].read_text())
    assert saved["expected"] == "fail" and saved["context"]["files"][0]["path"] == "src/a.py"


def test_render_text_with_nothing():
    assert replay.render_text(replay.Replay(), "o/r").startswith("no merged pull requests")
