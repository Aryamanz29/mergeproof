"""Run mergeproof as a GitHub App.

Install the App on a repository, add ``mergeproof.yaml``, and the gate runs with no workflow in
that repository. The server receives webhooks, authenticates as the App, reads the policy from
the pull request's base branch through the API, evaluates the pull request and publishes the
comment, the commit status and the check run. Checks that need a checkout (``shell``) report as
not applicable in this mode.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import jwt
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from mergeproof import __version__, engine, policy
from mergeproof.checks.registry import Registry, load_registry
from mergeproof.providers import github
from mergeproof.report import Status

log = logging.getLogger("mergeproof.app")

PULL_REQUEST_ACTIONS = frozenset(
    {"opened", "synchronize", "reopened", "edited", "labeled", "unlabeled", "ready_for_review"}
)


@dataclass
class Settings:
    app_id: str
    private_key: str
    webhook_secret: str
    policy_path: str = "mergeproof.yaml"
    api_url: str = github.API_URL
    comment: bool = True
    status: bool = True
    check_run: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        key = os.environ.get("MERGEPROOF_APP_PRIVATE_KEY", "")
        key_file = os.environ.get("MERGEPROOF_APP_PRIVATE_KEY_FILE")
        if not key and key_file:
            key = Path(key_file).read_text(encoding="utf-8")
        values = {
            "MERGEPROOF_APP_ID": os.environ.get("MERGEPROOF_APP_ID", ""),
            "MERGEPROOF_APP_PRIVATE_KEY": key,
            "MERGEPROOF_WEBHOOK_SECRET": os.environ.get("MERGEPROOF_WEBHOOK_SECRET", ""),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError("missing environment: " + ", ".join(missing))
        return cls(
            app_id=values["MERGEPROOF_APP_ID"],
            private_key=key.replace("\\n", "\n"),
            webhook_secret=values["MERGEPROOF_WEBHOOK_SECRET"],
            policy_path=os.environ.get("MERGEPROOF_POLICY", "mergeproof.yaml"),
            api_url=os.environ.get("GITHUB_API_URL", github.API_URL),
        )


class AppAuth:
    """Signs App JWTs and caches installation tokens until shortly before they expire."""

    def __init__(self, app_id: str, private_key: str, api_url: str = github.API_URL, timeout: float = 30.0) -> None:
        self.app_id = app_id
        self.private_key = private_key
        self._http = httpx.Client(
            base_url=api_url,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "mergeproof-app"},
        )
        self._tokens: dict[int, tuple[str, float]] = {}

    def app_jwt(self) -> str:
        now = int(time.time())
        return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": self.app_id}, self.private_key, algorithm="RS256")

    def installation_token(self, installation_id: int) -> str:
        cached = self._tokens.get(installation_id)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        response = self._http.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {self.app_jwt()}"},
        )
        response.raise_for_status()
        data = response.json()
        expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
        self._tokens[installation_id] = (data["token"], expires)
        return str(data["token"])


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature[len("sha256=") :])


def pull_request_numbers(event: str, payload: dict[str, Any]) -> list[int]:
    """Which pull requests an event should re-evaluate, if any."""
    action = payload.get("action")
    if event == "pull_request" and action in PULL_REQUEST_ACTIONS:
        return [int(payload["pull_request"]["number"])]
    if event == "pull_request_review" and action in {"submitted", "edited"}:
        return [int(payload["pull_request"]["number"])]
    if event == "issue_comment" and action in {"created", "edited"} and "pull_request" in payload.get("issue", {}):
        return [int(payload["issue"]["number"])]
    if event in {"check_suite", "check_run"} and action in {"completed", "rerequested"}:
        repo_id = payload.get("repository", {}).get("id")
        subject = payload.get(event) or {}
        return [
            int(pr["number"])
            for pr in subject.get("pull_requests", [])
            if pr.get("base", {}).get("repo", {}).get("id") == repo_id
        ]
    return []


def load_policy(client: github.Client, repo: str, ref: str, path: str) -> policy.Policy | None:
    """The policy as it stands on *ref*, normally the base branch, so a PR cannot edit its own rules."""
    try:
        data = client.get(f"/repos/{repo}/contents/{path}", ref=ref)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise
    text = base64.b64decode(data["content"]).decode("utf-8")
    return policy.loads(text, f"{repo}:{path}@{ref}")


@dataclass
class Gate:
    settings: Settings
    auth: AppAuth
    registry: Registry = field(default_factory=load_registry)

    def handle(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        numbers = pull_request_numbers(event, payload)
        if not numbers:
            return {"ignored": event}
        repo = payload["repository"]["full_name"]
        token = self.auth.installation_token(int(payload["installation"]["id"]))
        client = github.Client(token, self.settings.api_url)
        return {"repo": repo, "results": {number: self.evaluate(client, repo, number) for number in numbers}}

    def evaluate(self, client: github.Client, repo: str, number: int) -> dict[str, Any]:
        ctx = github.fetch(client, repo, number).model_copy(update={"has_checkout": False})
        try:
            pol = load_policy(client, repo, ctx.base_ref, self.settings.policy_path)
        except policy.PolicyError as exc:
            return self.reject(client, repo, ctx.head_sha, f"invalid {self.settings.policy_path}: {exc}")
        if pol is None:
            return {"skipped": f"no {self.settings.policy_path} on {ctx.base_ref}"}
        problems = policy.problems(pol, self.registry)
        if problems:
            return self.reject(client, repo, ctx.head_sha, f"invalid {self.settings.policy_path}: {problems[0]}")
        report = engine.evaluate(pol, ctx, self.registry)
        report.policy_path = self.settings.policy_path
        published = github.publish_report(
            client,
            report,
            comment=self.settings.comment,
            status=self.settings.status,
            check_run=self.settings.check_run,
        )
        return {"verdict": report.verdict.value, **published}

    def reject(self, client: github.Client, repo: str, sha: str | None, message: str) -> dict[str, Any]:
        if sha and self.settings.status:
            github.set_commit_status(client, repo, sha, Status.FAIL, message, None)
        return {"error": message}


def run_gate(gate: Gate, event: str, payload: dict[str, Any]) -> None:
    try:
        log.info("%s -> %s", event, gate.handle(event, payload))
    except Exception:
        log.exception("gate failed for %s", event)


def create_app(settings: Settings, gate: Gate | None = None) -> Starlette:
    gate = gate or Gate(settings, AppAuth(settings.app_id, settings.private_key, settings.api_url))

    async def webhook(request: Request) -> JSONResponse | PlainTextResponse:
        body = await request.body()
        if not verify_signature(settings.webhook_secret, body, request.headers.get("X-Hub-Signature-256")):
            return PlainTextResponse("bad signature", status_code=401)
        event = request.headers.get("X-GitHub-Event", "")
        payload = json.loads(body)
        if event == "ping":
            return JSONResponse({"pong": True})
        if not pull_request_numbers(event, payload):
            return JSONResponse({"ignored": event})
        return JSONResponse(
            {"accepted": True}, status_code=202, background=BackgroundTask(run_gate, gate, event, payload)
        )

    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "version": __version__})

    async def index(request: Request) -> PlainTextResponse:
        return PlainTextResponse(f"mergeproof {__version__}. GitHub App endpoint; webhooks go to POST /webhook.\n")

    return Starlette(
        routes=[Route("/", index), Route("/healthz", healthz), Route("/webhook", webhook, methods=["POST"])]
    )


def serve(host: str = "0.0.0.0", port: int = 8080) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(create_app(Settings.from_env()), host=host, port=port, log_level="info")
