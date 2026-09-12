import base64
import hashlib
import hmac
import json
import time

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from mergeproof import github_app

API = "https://api.github.com"
POLICY = "rules:\n  - id: labelled\n    require: [{check: pr.labels, with: {any_of: [ok]}}]\n"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = (
        key.private_key_bytes
        if False
        else key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return pem.decode(), public.decode()


@pytest.fixture
def settings(keypair):
    return github_app.Settings(app_id="12345", private_key=keypair[0], webhook_secret="s3cret")


def signed(secret: str, payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": sig, "Content-Type": "application/json"}


def pr_payload(action="opened", number=7):
    return {
        "action": action,
        "pull_request": {"number": number},
        "repository": {"full_name": "o/r", "id": 99},
        "installation": {"id": 1},
    }


def mock_pull_request(labels=("ok",), policy=POLICY):
    respx.post(f"{API}/app/installations/1/access_tokens").mock(
        return_value=httpx.Response(201, json={"token": "ghs_x", "expires_at": "2099-01-01T00:00:00Z"})
    )
    respx.get(f"{API}/repos/o/r/pulls/7").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "fix: x",
                "body": "",
                "user": {"login": "dev"},
                "labels": [{"name": lbl} for lbl in labels],
                "base": {"ref": "main", "sha": "b" * 40},
                "head": {"sha": "a" * 40},
            },
        )
    )
    respx.get(f"{API}/repos/o/r/pulls/7/files").mock(
        return_value=httpx.Response(200, json=[{"filename": "x.py", "status": "modified"}])
    )
    respx.get(f"{API}/repos/o/r/issues/7/comments").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{API}/repos/o/r/pulls/7/reviews").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{API}/repos/o/r/pulls/7/comments").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{API}/repos/o/r/commits/{'a' * 40}/check-runs").mock(
        return_value=httpx.Response(200, json={"check_runs": []})
    )
    if policy is None:
        respx.get(f"{API}/repos/o/r/contents/mergeproof.yaml").mock(return_value=httpx.Response(404, json={}))
    else:
        respx.get(f"{API}/repos/o/r/contents/mergeproof.yaml").mock(
            return_value=httpx.Response(200, json={"content": base64.b64encode(policy.encode()).decode()})
        )
    return {
        "comment": respx.post(f"{API}/repos/o/r/issues/7/comments").mock(
            return_value=httpx.Response(201, json={"html_url": "https://c/1"})
        ),
        "status": respx.post(f"{API}/repos/o/r/statuses/{'a' * 40}").mock(return_value=httpx.Response(201, json={})),
        "check": respx.post(f"{API}/repos/o/r/check-runs").mock(
            return_value=httpx.Response(201, json={"html_url": "https://k/1"})
        ),
    }


def test_signature_verification():
    body = b'{"a":1}'
    good = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
    assert github_app.verify_signature("s", body, good)
    assert not github_app.verify_signature("s", body, "sha256=deadbeef")
    assert not github_app.verify_signature("s", body, None)
    assert not github_app.verify_signature("s", body, "sha1=abc")


def test_app_jwt_is_signed_with_the_private_key(keypair):
    auth = github_app.AppAuth("12345", keypair[0])
    claims = jwt.decode(auth.app_jwt(), keypair[1], algorithms=["RS256"], options={"verify_exp": False})
    assert claims["iss"] == "12345" and claims["exp"] - claims["iat"] == 600
    assert claims["iat"] <= int(time.time())


@respx.mock
def test_installation_tokens_are_cached_until_near_expiry(keypair):
    route = respx.post(f"{API}/app/installations/1/access_tokens").mock(
        return_value=httpx.Response(201, json={"token": "ghs_x", "expires_at": "2099-01-01T00:00:00Z"})
    )
    auth = github_app.AppAuth("12345", keypair[0])
    assert auth.installation_token(1) == "ghs_x" and auth.installation_token(1) == "ghs_x"
    assert route.call_count == 1
    assert route.calls[0].request.headers["Authorization"].startswith("Bearer ")


def test_which_events_trigger_an_evaluation():
    f = github_app.pull_request_numbers
    assert f("pull_request", pr_payload("synchronize")) == [7]
    assert f("pull_request", pr_payload("closed")) == []
    assert f("issue_comment", {"action": "created", "issue": {"number": 3, "pull_request": {}}}) == [3]
    assert f("issue_comment", {"action": "created", "issue": {"number": 3}}) == []
    assert f("pull_request_review", {"action": "submitted", "pull_request": {"number": 4}}) == [4]
    suite = {
        "action": "completed",
        "repository": {"id": 99},
        "check_suite": {
            "pull_requests": [
                {"number": 5, "base": {"repo": {"id": 99}}},
                {"number": 6, "base": {"repo": {"id": 1}}},  # a fork's PR against another repo
            ]
        },
    }
    assert f("check_suite", suite) == [5]
    assert f("push", {}) == []


@respx.mock
def test_webhook_evaluates_and_publishes(settings):
    routes = mock_pull_request()
    client = TestClient(github_app.create_app(settings))
    body, headers = signed("s3cret", pr_payload())
    response = client.post("/webhook", content=body, headers={**headers, "X-GitHub-Event": "pull_request"})
    assert response.status_code == 202 and response.json() == {"accepted": True}
    assert routes["comment"].called and routes["status"].called and routes["check"].called
    status = json.loads(routes["status"].calls[0].request.content)
    assert status["state"] == "success" and status["context"] == "mergeproof"
    assert status["target_url"] == "https://c/1"


@respx.mock
def test_webhook_failing_policy_sets_failure_status(settings):
    routes = mock_pull_request(labels=())
    client = TestClient(github_app.create_app(settings))
    body, headers = signed("s3cret", pr_payload())
    client.post("/webhook", content=body, headers={**headers, "X-GitHub-Event": "pull_request"})
    assert json.loads(routes["status"].calls[0].request.content)["state"] == "failure"
    check = json.loads(routes["check"].calls[0].request.content)
    assert check["conclusion"] == "failure" and "0 of 1" in check["output"]["title"]


@respx.mock
def test_repositories_without_a_policy_are_left_alone(settings):
    routes = mock_pull_request(policy=None)
    gate = github_app.Gate(settings, github_app.AppAuth("12345", settings.private_key))
    result = gate.handle("pull_request", pr_payload())
    assert result["results"][7] == {"skipped": "no mergeproof.yaml on main"}
    assert not routes["comment"].called and not routes["status"].called


@respx.mock
def test_invalid_policy_is_reported_as_a_failed_status(settings):
    routes = mock_pull_request(policy="rules:\n  - id: a\n    require: [{check: nope}]\n")
    gate = github_app.Gate(settings, github_app.AppAuth("12345", settings.private_key))
    result = gate.handle("pull_request", pr_payload())
    assert "invalid mergeproof.yaml" in result["results"][7]["error"]
    sent = json.loads(routes["status"].calls[0].request.content)
    assert sent["state"] == "failure" and "unknown check" in sent["description"]
    assert not routes["comment"].called


def test_webhook_rejects_bad_signatures_and_ignores_other_events(settings):
    client = TestClient(github_app.create_app(settings))
    assert client.post("/webhook", content=b"{}", headers={"X-Hub-Signature-256": "sha256=00"}).status_code == 401
    body, headers = signed("s3cret", {"zen": "keep it logically awesome"})
    assert client.post("/webhook", content=body, headers={**headers, "X-GitHub-Event": "ping"}).json() == {"pong": True}
    body, headers = signed("s3cret", {"action": "created"})
    assert client.post("/webhook", content=body, headers={**headers, "X-GitHub-Event": "star"}).json() == {
        "ignored": "star"
    }
    assert client.get("/healthz").json()["ok"] is True
    assert "webhooks go to POST /webhook" in client.get("/").text


def test_settings_from_env(monkeypatch, keypair, tmp_path):
    for var in (
        "MERGEPROOF_APP_ID",
        "MERGEPROOF_APP_PRIVATE_KEY",
        "MERGEPROOF_APP_PRIVATE_KEY_FILE",
        "MERGEPROOF_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="MERGEPROOF_APP_ID, MERGEPROOF_APP_PRIVATE_KEY, MERGEPROOF_WEBHOOK_SECRET"):
        github_app.Settings.from_env()
    key_file = tmp_path / "key.pem"
    key_file.write_text(keypair[0])
    monkeypatch.setenv("MERGEPROOF_APP_ID", "1")
    monkeypatch.setenv("MERGEPROOF_APP_PRIVATE_KEY_FILE", str(key_file))
    monkeypatch.setenv("MERGEPROOF_WEBHOOK_SECRET", "s")
    settings = github_app.Settings.from_env()
    assert settings.private_key == keypair[0] and settings.policy_path == "mergeproof.yaml"
