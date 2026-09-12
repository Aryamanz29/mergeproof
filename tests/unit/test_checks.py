import re

import pytest

from mergeproof.checks.agent_verdict import AgentVerdict
from mergeproof.checks.body import Body
from mergeproof.checks.ci_job import CiJobPassed
from mergeproof.checks.evidence_field import EvidenceField
from mergeproof.checks.evidence_links import EvidenceLinks
from mergeproof.checks.files import FilesChanged
from mergeproof.checks.human_verified import HumanVerified
from mergeproof.checks.labels import Labels
from mergeproof.checks.shell import Shell
from mergeproof.checks.tests_changed import TestsChanged
from mergeproof.context import CheckRun, Comment
from mergeproof.report import Status

from .conftest import HEAD, make_context, run_check

MAP = {"src/{pkg}/{name}.py": "tests/**/test_{name}*.py"}


class TestTestsChanged:
    def test_each_mapped_file_needs_a_test(self):
        ctx = make_context(files=["src/api/users.py", "src/api/orders.py", "tests/unit/test_orders.py"])
        out = run_check(TestsChanged(), ctx, map=MAP)
        assert out.status == Status.FAIL
        assert out.data["missing"] == {"src/api/users.py": "tests/**/test_users*.py"}

    def test_missing_tests_are_annotated_on_the_source_file(self):
        ctx = make_context(files=["src/api/users.py"])
        out = run_check(TestsChanged(), ctx, map=MAP)
        assert [a.path for a in out.annotations] == ["src/api/users.py"]
        assert out.annotations[0].line == 1 and "tests/**/test_users*.py" in out.annotations[0].message
        covered = make_context(files=["src/api/users.py", "tests/test_users.py"])
        assert run_check(TestsChanged(), covered, map=MAP).annotations == []

    def test_pass_skip_and_ignore(self):
        ctx = make_context(files=["src/api/users.py", "tests/unit/api/test_users_extra.py"])
        assert run_check(TestsChanged(), ctx, map=MAP).status == Status.PASS
        assert run_check(TestsChanged(), make_context(files=["README.md"]), map=MAP).status == Status.SKIP
        ctx = make_context(files=["src/api/generated.py"])
        assert run_check(TestsChanged(), ctx, map=MAP, ignore=["src/api/generated.py"]).status == Status.SKIP

    def test_any_of_mode(self):
        assert run_check(TestsChanged(), make_context(files=["src/a.py"]), any_of=["tests/**"]).status == Status.FAIL
        ctx = make_context(files=["src/a.py", "tests/test_a.py"])
        assert run_check(TestsChanged(), ctx, any_of=["tests/**"]).status == Status.PASS

    def test_explain_mentions_mapping(self):
        text = TestsChanged().explain(TestsChanged.Params(map=MAP))
        assert "src/{pkg}/{name}.py" in text


class TestFilesChanged:
    def test_any_all_none(self):
        ctx = make_context(files=["db/migrations/001.sql", "CHANGELOG.md"])
        assert run_check(FilesChanged(), ctx, all_of=["CHANGELOG.md"]).status == Status.PASS
        assert run_check(FilesChanged(), ctx, any_of=["docs/**"]).status == Status.FAIL
        out = run_check(FilesChanged(), ctx, none_of=["db/migrations/**"])
        assert out.status == Status.FAIL and "must not change" in out.summary


class TestEvidenceField:
    def test_presence_and_constraints(self, evidence_body):
        ctx = make_context(body=evidence_body(environment="staging", image="registry/app:pr-7", tags=["a"]))
        assert run_check(EvidenceField(), ctx, key="environment", equals="staging").status == Status.PASS
        assert run_check(EvidenceField(), ctx, key="environment", equals="prod").status == Status.FAIL
        assert run_check(EvidenceField(), ctx, key="environment", one_of=["prod", "staging"]).status == Status.PASS
        assert run_check(EvidenceField(), ctx, key="image", matches=r":pr-\d+$").status == Status.PASS
        assert run_check(EvidenceField(), ctx, key="image", matches=r":v\d").status == Status.FAIL
        assert run_check(EvidenceField(), ctx, key="tags", min_items=1).status == Status.PASS
        assert run_check(EvidenceField(), ctx, key="tags", min_items=2).status == Status.FAIL
        out = run_check(EvidenceField(), ctx, key="absent")
        assert out.status == Status.FAIL and "missing" in out.summary
        out = run_check(EvidenceField(), make_context(body="nothing"), key="environment")
        assert "no ```evidence block" in out.summary
        out = run_check(EvidenceField(), make_context(body="```evidence\n- x\n```"), key="environment")
        assert out.status == Status.FAIL and out.details

    def test_template_is_nested_and_uses_hints(self):
        check = EvidenceField()
        assert check.evidence_template(check.Params(key="image.tag", example="pr-1")) == {"image": {"tag": "pr-1"}}
        assert check.evidence_template(check.Params(key="env", equals="staging")) == {"env": "staging"}
        assert check.evidence_template(check.Params(key="env", one_of=["a", "b"])) == {"env": "a"}
        assert check.evidence_template(check.Params(key="items", min_items=1)) == {"items": ["<item>"]}
        assert check.evidence_template(check.Params(key="x")) == {"x": "<value>"}


def links_body(pairs, key="links"):
    items = "\n".join(f"  - before: {b}\n    after: {a}" for b, a in pairs)
    return f"```evidence\n{key}:\n{items}\n```"


class StubVerifier:
    def __init__(self, known, raise_for=()):
        self.known = set(known)
        self.raise_for = set(raise_for)

    def verify(self, url, match):
        if url in self.raise_for:
            raise RuntimeError("boom")
        return url in self.known


class TestEvidenceLinks:
    def test_valid_pairs(self):
        ctx = make_context(body=links_body([("https://x/1", "https://x/2")]))
        out = run_check(EvidenceLinks(), ctx)
        assert out.status == Status.PASS and out.data["pairs"][0]["after"] == "https://x/2"

    def test_rejections(self):
        same = links_body([("https://x/1", "https://x/1")])
        assert "same link" in run_check(EvidenceLinks(), make_context(body=same)).details[0]
        assert run_check(EvidenceLinks(), make_context(body="")).status == Status.FAIL
        out = run_check(EvidenceLinks(), make_context(body=links_body([("https://x/1", "https://x/2")])), min_pairs=2)
        assert "need 2" in out.summary
        bad = "```evidence\nlinks:\n  - after: ftp://x\n  - nope\n```"
        out = run_check(EvidenceLinks(), make_context(body=bad), require_before=False)
        assert out.status == Status.FAIL and len(out.details) == 2

    def test_pattern_with_named_groups(self):
        pattern = r"^(?P<host>https://logs\.example\.com)/run/(?P<run_id>\d+)$"
        good = links_body([("https://logs.example.com/run/1", "https://logs.example.com/run/2")])
        assert run_check(EvidenceLinks(), make_context(body=good), pattern=pattern).status == Status.PASS
        other = links_body([("https://elsewhere/run/1", "https://logs.example.com/run/2")])
        assert run_check(EvidenceLinks(), make_context(body=other), pattern=pattern).status == Status.FAIL

    def test_after_only_mode(self):
        body = "```evidence\nlinks:\n  - after: https://x/2\n```"
        assert run_check(EvidenceLinks(), make_context(body=body), require_before=False).status == Status.PASS
        assert run_check(EvidenceLinks(), make_context(body=body)).status == Status.FAIL

    def test_verification_paths(self):
        ctx = make_context(body=links_body([("https://x/1", "https://x/2")]))
        check = EvidenceLinks()
        check.verifier = StubVerifier({"https://x/1", "https://x/2"})
        assert run_check(check, ctx, verify="stub").status == Status.PASS
        check.verifier = StubVerifier({"https://x/1"})
        out = run_check(check, ctx, verify="stub")
        assert out.status == Status.FAIL and "https://x/2" in out.details[0]
        check.verifier = StubVerifier({"https://x/2"}, raise_for={"https://x/1"})
        out = run_check(check, ctx, verify="stub")
        assert out.status == Status.FAIL and "RuntimeError" in out.details[0]
        assert run_check(EvidenceLinks(), ctx, verify="does-not-exist").status == Status.ERROR

    def test_template(self):
        check = EvidenceLinks()
        assert check.evidence_template(check.Params())["links"][0]["before"].startswith("https://")
        assert "before" not in check.evidence_template(check.Params(require_before=False))["links"][0]


class TestCiJobPassed:
    runs = [
        CheckRun(name="unit (3.12)", status="completed", conclusion="success"),
        CheckRun(name="unit (3.13)", status="in_progress"),
        CheckRun(name="lint", status="completed", conclusion="failure", url="https://ci/1"),
    ]

    def test_statuses(self):
        ctx = make_context(check_runs=self.runs)
        assert run_check(CiJobPassed(), ctx, name="lint").status == Status.FAIL
        assert run_check(CiJobPassed(), ctx, name="unit", regex=True).status == Status.PENDING
        assert run_check(CiJobPassed(), ctx, name=r"unit \(3\.12\)", regex=True).status == Status.PASS
        assert run_check(CiJobPassed(), ctx, name="missing").status == Status.PENDING
        assert run_check(CiJobPassed(), ctx, name="missing", missing="fail").status == Status.FAIL
        assert run_check(CiJobPassed(), ctx, name="unit (3.12)", min_matches=2).status == Status.FAIL
        assert run_check(CiJobPassed(), make_context(online=False), name="lint").status == Status.PENDING


class TestHumanVerified:
    def test_who_may_verify(self):
        check = HumanVerified()
        by_author = Comment(author="octocat", body=f"/verified {HEAD[:7]}")
        by_bot = Comment(author="claude[bot]", body=f"/verified {HEAD[:7]}")
        stale = Comment(author="reviewer", body="/verified 0000000")
        good = Comment(author="reviewer", body=f"opened both, /verified {HEAD[:7]}", url="https://c/1")

        out = run_check(check, make_context(comments=[by_author, by_bot, stale]))
        assert out.status == Status.PENDING and len(out.details) == 3
        out = run_check(check, make_context(comments=[good]))
        assert out.status == Status.PASS and out.data["by"] == "reviewer" and out.details == ["https://c/1"]
        assert run_check(check, make_context(comments=[stale]), bind_to_head=False).status == Status.PASS
        assert run_check(check, make_context(comments=[good]), allowed_users=["lead"]).status == Status.PENDING
        review = Comment(author="reviewer", body=f"/verified {HEAD[:7]}", kind="review", state="COMMENTED")
        assert (
            run_check(check, make_context(comments=[review]), require_review_state="APPROVED").status == Status.PENDING
        )
        review.state = "APPROVED"
        assert run_check(check, make_context(comments=[review]), require_review_state="APPROVED").status == Status.PASS
        assert run_check(check, make_context(online=False)).status == Status.PENDING


def verdict(author, head=HEAD[:7], verdict="pass", confidence=0.9, at="2026-01-01T00:00:00Z", name="review"):
    text = f"```verdict\ncheck: {name}\nverdict: {verdict}\nhead: {head}\nconfidence: {confidence}\nsummary: ok\n```"
    return Comment(author=author, body=text, created_at=at)


class TestAgentVerdict:
    bot = "github-actions[bot]"

    def test_verdicts(self):
        check = AgentVerdict()
        assert run_check(check, make_context(), name="review").status == Status.PENDING
        assert (
            run_check(check, make_context(comments=[verdict(self.bot)]), name="review", authors=[self.bot]).status
            == Status.PASS
        )
        out = run_check(check, make_context(comments=[verdict("rando")]), name="review", authors=[self.bot])
        assert out.status == Status.PENDING and "not an allowed" in out.details[0]
        assert (
            run_check(check, make_context(comments=[verdict(self.bot, head="0000000")]), name="review").status
            == Status.PENDING
        )
        assert (
            run_check(check, make_context(comments=[verdict(self.bot, verdict="fail")]), name="review").status
            == Status.FAIL
        )
        low = verdict(self.bot, confidence=0.4)
        assert (
            run_check(check, make_context(comments=[low]), name="review", min_confidence=0.8).status == Status.PENDING
        )
        assert (
            run_check(check, make_context(comments=[verdict(self.bot, name="other")]), name="review").status
            == Status.PENDING
        )
        assert run_check(check, make_context(online=False), name="review").status == Status.PENDING

    def test_latest_verdict_wins(self):
        comments = [
            verdict(self.bot, verdict="fail", at="2026-01-01T00:00:00Z"),
            verdict(self.bot, verdict="pass", at="2026-01-02T00:00:00Z"),
        ]
        assert run_check(AgentVerdict(), make_context(comments=comments), name="review").status == Status.PASS


class TestLabelsAndBody:
    def test_labels(self):
        ctx = make_context(labels=["a", "b"])
        assert run_check(Labels(), ctx, any_of=["a"], all_of=["a", "b"], none_of=["c"]).status == Status.PASS
        out = run_check(Labels(), ctx, any_of=["z"], all_of=["c"], none_of=["b"])
        assert out.status == Status.FAIL and out.summary.count(";") == 2

    def test_body(self):
        ctx = make_context(body="## Summary\nx\n## Rollback\nrun down.sql\n")
        assert run_check(Body(), ctx, sections=["Summary", "Rollback"]).status == Status.PASS
        assert run_check(Body(), ctx, sections=["Testing"]).status == Status.FAIL
        assert run_check(Body(), ctx, matches=r"down\.sql").status == Status.PASS
        assert run_check(Body(), ctx, min_length=500).status == Status.FAIL


class TestShell:
    def test_exit_codes_and_env(self, tmp_path):
        ctx = make_context(files=["a.py", "b.py"], root=str(tmp_path))
        out = run_check(Shell(), ctx, run='test "$(printf "%s" "$MERGEPROOF_FILES" | wc -l | tr -d " ")" = 1')
        assert out.status == Status.PASS, out
        out = run_check(Shell(), ctx, run="echo nope; exit 3")
        assert out.status == Status.FAIL and out.details == ["nope"] and "3" in out.summary
        assert run_check(Shell(), ctx, run="sleep 5", timeout=1).status == Status.ERROR


@pytest.mark.parametrize("check", [CiJobPassed, HumanVerified, AgentVerdict])
def test_github_only_checks_are_flagged(check):
    assert check.needs_github


def test_all_checks_have_ids_and_descriptions(registry):
    for check_id, cls in registry.items():
        assert re.fullmatch(r"[a-z_]+(\.[a-z_]+)?", check_id)
        assert cls.description
