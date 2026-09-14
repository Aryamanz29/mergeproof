import base64
import json

import httpx
import pytest
import respx

from mergeproof import receipt
from mergeproof.providers import github
from mergeproof.report import Outcome, Report, RequirementResult, RuleResult, Status

API = "https://api.github.com"
MERGE = "c" * 40


def merged_report() -> Report:
    req = RequirementResult(
        label="unit tests touched",
        check="tests.changed",
        severity="block",
        outcome=Outcome(status=Status.PASS, summary="tests changed for all 1 mapped source file", details=["src/a.py"]),
    )
    rule = RuleResult(id="source-needs-tests", severity="block", matched=True, files=["src/a.py"], requirements=[req])
    return Report(
        source="github",
        repo="o/r",
        number=7,
        head_sha="a" * 40,
        base_ref="main",
        merged=True,
        merge_commit_sha=MERGE,
        merged_at="2026-09-14T18:02:25Z",
        merged_by="lead",
        policy_sha256="9c1d3a2e0b7f" + "0" * 52,
        rules=[rule],
    )


def test_build_carries_the_merge_and_the_report():
    doc = receipt.build(merged_report(), run_url="https://run")
    meta = doc["receipt"]
    assert meta["merge_commit_sha"] == MERGE and meta["pull_request"] == 7 and meta["merged_by"] == "lead"
    assert meta["verdict"] == "pass" and meta["policy_sha256"].startswith("9c1d3a2e0b7f") and meta["run_url"]
    assert doc["report"]["rules"][0]["id"] == "source-needs-tests"
    assert receipt.path_for(MERGE) == f"receipts/{MERGE}.json"
    text = receipt.summary(doc)
    assert "#7 merged as ccccccc by lead" in text and "[   pass] source-needs-tests" in text


@respx.mock
def test_write_creates_the_branch_the_first_time_and_appends_afterwards():
    client = github.Client("tok")
    respx.post(f"{API}/repos/o/r/git/blobs").mock(return_value=httpx.Response(201, json={"sha": "blob"}))
    tree = respx.post(f"{API}/repos/o/r/git/trees").mock(return_value=httpx.Response(201, json={"sha": "tree"}))
    commit = respx.post(f"{API}/repos/o/r/git/commits").mock(return_value=httpx.Response(201, json={"sha": "new"}))
    ref = respx.get(f"{API}/repos/o/r/git/ref/heads/mergeproof-receipts")
    create_ref = respx.post(f"{API}/repos/o/r/git/refs").mock(return_value=httpx.Response(201, json={}))
    update_ref = respx.patch(f"{API}/repos/o/r/git/refs/heads/mergeproof-receipts").mock(
        return_value=httpx.Response(200, json={})
    )
    doc = receipt.build(merged_report())

    ref.mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
    url = receipt.write(client, "o/r", doc)
    assert url == f"https://github.com/o/r/blob/mergeproof-receipts/receipts/{MERGE}.json"
    assert create_ref.called and not update_ref.called
    assert json.loads(commit.calls[0].request.content)["parents"] == []
    assert "base_tree" not in json.loads(tree.calls[0].request.content)

    ref.mock(return_value=httpx.Response(200, json={"object": {"sha": "head"}}))
    respx.get(f"{API}/repos/o/r/git/commits/head").mock(return_value=httpx.Response(200, json={"tree": {"sha": "t0"}}))
    receipt.write(client, "o/r", doc)
    assert update_ref.called
    assert json.loads(commit.calls[1].request.content)["parents"] == ["head"]
    assert json.loads(tree.calls[1].request.content)["base_tree"] == "t0"
    assert json.loads(commit.calls[1].request.content)["message"] == "receipt: #7 merged as ccccccc"


@respx.mock
def test_read_by_sha_and_by_pull_request_number():
    client = github.Client("tok")
    doc = receipt.build(merged_report())
    encoded = base64.b64encode(json.dumps(doc).encode()).decode()
    respx.get(f"{API}/repos/o/r/contents/receipts/{MERGE}.json").mock(
        return_value=httpx.Response(200, json={"content": encoded})
    )
    respx.get(f"{API}/repos/o/r/pulls/7").mock(
        return_value=httpx.Response(200, json={"merged_at": "t", "merge_commit_sha": MERGE})
    )
    respx.get(f"{API}/repos/o/r/pulls/8").mock(return_value=httpx.Response(200, json={"merged_at": None}))
    respx.get(f"{API}/repos/o/r/contents/receipts/{'d' * 40}.json").mock(return_value=httpx.Response(404, json={}))

    assert receipt.read(client, "o/r", MERGE)["receipt"]["pull_request"] == 7
    assert receipt.read(client, "o/r", "#7")["receipt"]["pull_request"] == 7
    assert receipt.read(client, "o/r", "7")["receipt"]["pull_request"] == 7
    with pytest.raises(LookupError, match="not merged"):
        receipt.read(client, "o/r", "#8")
    with pytest.raises(LookupError, match="no receipt"):
        receipt.read(client, "o/r", "d" * 40)
