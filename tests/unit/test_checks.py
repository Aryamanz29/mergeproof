import re

import pytest

from mergeproof.checks.agent_verdict import AgentVerdict
from mergeproof.checks.body import Body
from mergeproof.checks.ci_job import CiJobPassed
from mergeproof.checks.eval_score import EvalRun, EvalScore, MissingCredentials
from mergeproof.checks.evidence_artifacts import EvidenceArtifacts
from mergeproof.checks.evidence_field import EvidenceField
from mergeproof.checks.evidence_links import EvidenceLinks
from mergeproof.checks.files import FilesChanged
from mergeproof.checks.human_verified import HumanVerified
from mergeproof.checks.labels import Labels
from mergeproof.checks.shell import Shell
from mergeproof.checks.tests_changed import TestsChanged
from mergeproof.context import CheckRun, Comment
from mergeproof.report import Status
from mergeproof.verifiers import Verification

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

    def test_existing_only_skips_sources_without_a_test_module(self):
        tree = ["src/api/users.py", "src/api/orders.py", "tests/unit/test_users.py"]
        ctx = make_context(files=["src/api/users.py", "src/api/orders.py"], tree=tree)
        strict = run_check(TestsChanged(), ctx, map=MAP)
        assert strict.status == Status.FAIL and set(strict.data["missing"]) == {"src/api/users.py", "src/api/orders.py"}
        lenient = run_check(TestsChanged(), ctx, map=MAP, existing_only=True)
        assert lenient.status == Status.FAIL and list(lenient.data["missing"]) == ["src/api/users.py"]
        ctx = make_context(files=["src/api/users.py", "tests/unit/test_users.py", "src/api/orders.py"], tree=tree)
        out = run_check(TestsChanged(), ctx, map=MAP, existing_only=True)
        assert out.status == Status.PASS and "1 file without a test module skipped" in out.summary
        ctx = make_context(files=["src/api/orders.py"], tree=tree)
        out = run_check(TestsChanged(), ctx, map=MAP, existing_only=True)
        assert out.status == Status.SKIP and "no test module yet" in out.summary
        unknown_tree = make_context(files=["src/api/orders.py"])
        assert run_check(TestsChanged(), unknown_tree, map=MAP, existing_only=True).status == Status.FAIL

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
        assert FilesChanged().explain(FilesChanged.Params(all_of=["CHANGELOG.md"])) == "Change `CHANGELOG.md`."


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
        assert "no `evidence` block" in out.summary
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
    def __init__(self, known, raise_for=(), rich=()):
        self.known = set(known)
        self.raise_for = set(raise_for)
        self.rich = set(rich)

    def verify(self, url, match):
        if url in self.raise_for:
            raise RuntimeError("boom")
        if url in self.rich:
            return Verification(found=True, source="tracer", id="t1", size="14 spans", at="2026-09-14T17:02Z")
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
        check.verifier = StubVerifier({"https://x/1", "https://x/2"}, rich={"https://x/2"})
        out = run_check(check, ctx, verify="stub")
        assert out.status == Status.PASS
        assert out.details == ["before: stub", "after: tracer · 14 spans · 2026-09-14T17:02Z"]
        assert out.data["verified"][1] == {
            "found": True,
            "source": "tracer",
            "id": "t1",
            "at": "2026-09-14T17:02Z",
            "size": "14 spans",
            "facts": {},
        }
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


class TestEvidenceArtifacts:
    def body(self, yaml_text):
        return f"```evidence\n{yaml_text}\n```"

    def test_pair_kind_is_evidence_links(self):
        body = links_body([("https://x/1", "https://x/2")])
        via_links = run_check(EvidenceLinks(), make_context(body=body))
        via_kind = run_check(EvidenceArtifacts(), make_context(body=body), key="links", kind="pair")
        assert via_kind.status == via_links.status == Status.PASS
        assert via_kind.summary == via_links.summary and via_kind.data == via_links.data

    def test_single(self):
        check = EvidenceArtifacts()
        out = run_check(
            check, make_context(body=self.body("preview: https://pr-1.example.com")), key="preview", kind="single"
        )
        assert (
            out.status == Status.PASS
            and out.summary == "1 link"
            and out.data == {"links": ["https://pr-1.example.com"]}
        )
        mapping = self.body("preview:\n  what: checkout\n  url: https://pr-1.example.com")
        assert run_check(check, make_context(body=mapping), key="preview", kind="single").status == Status.PASS
        out = run_check(check, make_context(body=self.body("preview: ftp://x")), key="preview", kind="single")
        assert out.status == Status.FAIL and "does not look like an accepted link" in out.details[0]
        out = run_check(
            check, make_context(body=self.body("preview: [https://a, https://b]")), key="preview", kind="single"
        )
        assert out.status == Status.FAIL and "expected one link, got a list" in out.details[0]
        out = run_check(check, make_context(body=""), key="preview", kind="single")
        assert out.status == Status.FAIL and "no `preview` value" in out.summary
        assert (
            run_check(
                check, make_context(body=self.body("preview: https://x")), key="preview", kind="single", min_items=5
            ).status
            == Status.PASS
        )

    def test_set(self):
        check = EvidenceArtifacts()
        shots = self.body("screens:\n  - https://s/1.png\n  - what: cart\n    url: https://s/2.png")
        out = run_check(check, make_context(body=shots), key="screens", kind="set", min_items=2)
        assert (
            out.status == Status.PASS
            and out.summary == "2 links"
            and out.data["links"] == ["https://s/1.png", "https://s/2.png"]
        )
        out = run_check(check, make_context(body=shots), key="screens", kind="set", min_items=3)
        assert out.status == Status.FAIL and "2 valid links, need 3" in out.summary
        out = run_check(check, make_context(body=self.body("screens: https://s/1.png")), key="screens", kind="set")
        assert out.status == Status.FAIL and "expected a list" in out.details[0]
        out = run_check(check, make_context(body=self.body("screens:\n  - what: cart")), key="screens", kind="set")
        assert out.status == Status.FAIL and "item 1: missing `url`" in out.details[0]
        pattern = r"^https://s/.*\.png$"
        out = run_check(check, make_context(body=shots), key="screens", kind="set", pattern=pattern, min_items=2)
        assert out.status == Status.PASS

    def test_verification_is_shared_across_kinds(self):
        check = EvidenceArtifacts()
        check.verifier = StubVerifier({"https://s/1.png"}, rich={"https://s/1.png"})
        shots = self.body("screens:\n  - https://s/1.png\n  - https://s/2.png")
        out = run_check(check, make_context(body=shots), key="screens", kind="set", verify="stub")
        assert out.status == Status.FAIL and out.details == ["link 2: not found at https://s/2.png"]
        one = self.body("preview: https://s/1.png")
        out = run_check(check, make_context(body=one), key="preview", kind="single", verify="stub")
        assert out.status == Status.PASS and out.summary == "1 link, all verified"
        assert (
            out.details == ["preview: tracer · 14 spans · 2026-09-14T17:02Z"]
            and out.data["verified"][0]["size"] == "14 spans"
        )
        assert (
            run_check(EvidenceArtifacts(), make_context(body=one), key="preview", kind="single", verify="nope").status
            == Status.ERROR
        )

    def test_templates_and_explanations_per_kind(self):
        check = EvidenceArtifacts()
        pair = check.evidence_template(check.Params(key="traces"))
        assert pair == {
            "traces": [
                {"what": "<what was exercised>", "before": check.Params().example, "after": check.Params().example}
            ]
        }
        single = check.evidence_template(check.Params(key="preview", kind="single", example="https://p"))
        assert single == {"preview": {"what": "<what was exercised>", "url": "https://p"}}
        many = check.evidence_template(check.Params(key="screens", kind="set", example="https://s"))
        assert many == {"screens": [{"what": "<what was exercised>", "url": "https://s"}]}
        assert check.explain(check.Params(key="preview", kind="single", pattern="^https://")) == (
            "A link under `preview` in the evidence block, matching `^https://`."
        )
        assert check.explain(check.Params(key="screens", kind="set", min_items=2, verify="http")) == (
            "At least 2 links under `screens` in the evidence block; links are verified with `http`."
        )
        assert "Put the link under `preview`" in check.fix(check.Params(key="preview", kind="single"))


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

    def test_only_the_newest_run_per_name_counts(self):
        runs = [
            CheckRun(name="unit (3.12)", status="completed", conclusion="cancelled", started_at="2026-01-01T10:00:00Z"),
            CheckRun(name="unit (3.12)", status="completed", conclusion="success", started_at="2026-01-01T10:05:00Z"),
            CheckRun(name="integration", status="completed", conclusion="success", started_at="2026-01-01T10:00:00Z"),
            CheckRun(name="integration", status="in_progress", started_at="2026-01-01T10:05:00Z"),
        ]
        ctx = make_context(check_runs=runs)
        assert run_check(CiJobPassed(), ctx, name="unit (3.12)").status == Status.PASS
        assert run_check(CiJobPassed(), ctx, name="integration").status == Status.PENDING
        superseded_failure = [
            CheckRun(name="lint", status="completed", conclusion="failure", started_at="2026-01-01T10:00:00Z"),
            CheckRun(name="lint", status="completed", conclusion="success", started_at="2026-01-01T10:09:00Z"),
        ]
        assert run_check(CiJobPassed(), make_context(check_runs=superseded_failure), name="lint").status == Status.PASS


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

    def test_approving_review_counts_when_accepted(self):
        check = HumanVerified()
        approved = Comment(author="reviewer", body="", kind="review", state="APPROVED", commit=HEAD, url="https://r/1")
        stale = Comment(author="reviewer", body="", kind="review", state="APPROVED", commit="0" * 40)
        requested_changes = Comment(author="reviewer", body="", kind="review", state="CHANGES_REQUESTED", commit=HEAD)
        by_bot = Comment(author="review[bot]", body="", kind="review", state="APPROVED", commit=HEAD)

        out = run_check(check, make_context(comments=[approved]))
        assert out.status == Status.PENDING, "approval is opt-in"
        out = run_check(check, make_context(comments=[approved]), accept_approval=True)
        assert out.status == Status.PASS and out.data["how"] == "approved" and out.details == ["https://r/1"]
        out = run_check(check, make_context(comments=[stale, requested_changes, by_bot]), accept_approval=True)
        assert out.status == Status.PENDING and len(out.details) == 2
        assert "older commit" in out.details[0]
        assert (
            run_check(check, make_context(comments=[stale]), accept_approval=True, bind_to_head=False).status
            == Status.PASS
        )
        assert "approving review" in out.summary
        assert "approves the pull request" in check.explain(check.Params(accept_approval=True))


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


def test_broken_plugin_entry_points_are_skipped(monkeypatch, capsys):
    from importlib.metadata import EntryPoint

    from mergeproof.checks import registry as registry_module

    broken = EntryPoint(name="x.broken", value="no_such_module:Check", group="mergeproof.checks")
    monkeypatch.setattr(registry_module, "entry_points", lambda group: [broken])
    reg = registry_module.load_registry()
    assert "x.broken" not in reg.ids() and "tests.changed" in reg.ids()
    assert "x.broken" in capsys.readouterr().err


def test_all_checks_have_ids_and_descriptions(registry):
    for check_id, cls in registry.items():
        assert re.fullmatch(r"[a-z_]+(\.[a-z_]+)?", check_id)
        assert cls.description


class StubEval(EvalScore):
    id = "stub.eval"
    source = "stub"
    runs = {
        "run-1": EvalRun(id="run-1", name="pr-7", at="2026-09-14T17:00:00Z", count=40, scores={"correctness": 0.91}),
        "run-0": EvalRun(id="run-0", name="main", scores={"correctness": 0.95}),
        "run-low": EvalRun(id="run-low", scores={"correctness": 0.4}),
    }

    class Params(EvalScore.Params):
        pattern: str | None = r"^https://evals\.example\.com/runs/(?P<run>[\w-]+)"

    def fetch_run(self, ref, match, params):
        key = match.group("run") if match else ref
        if key == "no-creds":
            raise MissingCredentials("STUB_KEY is not set")
        if key == "boom":
            raise RuntimeError("backend down")
        if key not in self.runs:
            raise ValueError(f"no run {key!r}")
        return self.runs[key]


def eval_body(ref, baseline=None):
    extra = f"\neval_baseline: {baseline}" if baseline else ""
    return f"```evidence\neval: {ref}{extra}\n```"


class TestEvalScore:
    def test_scores_against_thresholds_with_provenance(self):
        out = run_check(StubEval(), make_context(body=eval_body("run-1")), scorers={"correctness": 0.85})
        assert out.status == Status.PASS and out.summary == "stub run scores correctness 0.91"
        assert out.details == ["stub · pr-7 · 40 examples · 2026-09-14T17:00:00Z", "correctness 0.91 ≥ 0.85"]
        assert out.data["scores"] == {"correctness": 0.91} and out.data["run"]["name"] == "pr-7"
        by_url = make_context(body=eval_body("https://evals.example.com/runs/run-1"))
        assert run_check(StubEval(), by_url, scorers={"correctness": 0.85}).status == Status.PASS

    def test_below_bar_missing_scorer_and_regression(self):
        out = run_check(StubEval(), make_context(body=eval_body("run-low")), scorers={"correctness": 0.85})
        assert out.status == Status.FAIL and "correctness 0.40 is below 0.85" in out.summary
        assert out.details[1] == "correctness 0.40 < 0.85" and out.fix and "`eval`" in out.fix
        out = run_check(StubEval(), make_context(body=eval_body("run-1")), scorers={"safety": 0.9})
        assert out.status == Status.FAIL and "safety: not scored" in out.summary
        ctx = make_context(body=eval_body("run-1", baseline="run-0"))
        out = run_check(StubEval(), ctx, scorers={"correctness": 0.85}, max_regression=0.02)
        assert out.status == Status.FAIL and "dropped 0.04" in out.summary
        assert (
            out.details[1] == "correctness 0.91 ≥ 0.85 (baseline 0.95, -0.04)" and out.data["baseline"]["id"] == "run-0"
        )
        out = run_check(StubEval(), ctx, scorers={"correctness": 0.85}, max_regression=0.1)
        assert out.status == Status.PASS

    def test_missing_evidence_bad_link_credentials_and_errors(self):
        check = StubEval()
        assert run_check(check, make_context(body=""), scorers={"correctness": 0.8}).status == Status.FAIL
        out = run_check(check, make_context(body=eval_body("https://evals.example.com/other/1")), scorers={"c": 0.8})
        assert out.status == Status.FAIL and "does not look like a stub run link" in out.summary
        out = run_check(check, make_context(body=eval_body("no-creds")), scorers={"c": 0.8})
        assert out.status == Status.PENDING and "STUB_KEY" in out.summary
        out = run_check(check, make_context(body=eval_body("boom")), scorers={"c": 0.8})
        assert out.status == Status.ERROR and "RuntimeError" in out.summary
        out = run_check(check, make_context(body=eval_body("nope")), scorers={"c": 0.8})
        assert out.status == Status.FAIL and "no run 'nope'" in out.summary

    def test_explain_and_template(self):
        check = StubEval()
        params = check.Params(scorers={"correctness": 0.8, "safety": 0.95}, max_regression=0.05)
        assert check.explain(params) == (
            "An evaluation run named under `eval` in the evidence block scores `correctness` ≥ 0.8, `safety` ≥ 0.95"
            " on stub; with `eval_baseline`, no scorer drops by more than 0.05."
        )
        assert check.evidence_template(params) == {
            "eval": "<experiment id or URL>",
            "eval_baseline": "<experiment id or URL>",
        }
        assert check.evidence_template(check.Params(scorers={"c": 1})) == {"eval": "<experiment id or URL>"}
