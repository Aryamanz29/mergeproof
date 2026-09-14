"""Fixtures for tests that drive the installed CLI as a user would."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
CLI = [sys.executable, "-m", "mergeproof"]

pytestmark = pytest.mark.integration


def run_cli(*args: str, input: str | None = None, cwd: Path | None = None, env: dict | None = None):
    return subprocess.run([*CLI, *args], input=input, capture_output=True, text=True, cwd=cwd, env=env)


def scenarios():
    for path in sorted(EXAMPLES.glob("*/scenarios/*.json")):
        yield pytest.param(path, id=f"{path.parent.parent.name}/{path.stem}")


class LangfuseStub(BaseHTTPRequestHandler):
    """Answers the Langfuse endpoints the verifier and the eval check need, for fixed ids.

    Traces `trace-before-1` and `trace-after-1` exist (for the links verifier). Dataset
    `search-golden` has two runs: `pr-91` scores 0.9 and 0.8 on `correctness`, `pr-92` 0.6 and 0.5.
    """

    known = {"trace-before-1", "trace-after-1"}
    runs = {"pr-91": ["golden-1", "golden-2"], "pr-92": ["golden-3", "golden-4"]}
    correctness = {"golden-1": 0.9, "golden-2": 0.8, "golden-3": 0.6, "golden-4": 0.5}

    def do_GET(self):
        prefix = "/api/public/traces/"
        run_prefix = "/api/public/datasets/search-golden/runs/"
        trace_id = self.path[len(prefix) :] if self.path.startswith(prefix) else None
        if trace_id in self.known:
            body = json.dumps({"id": trace_id}).encode()
            self.send_response(200)
        elif trace_id in self.correctness:
            scores = [{"name": "correctness", "value": self.correctness[trace_id]}]
            body = json.dumps({"id": trace_id, "scores": scores}).encode()
            self.send_response(200)
        elif self.path.startswith(run_prefix) and self.path[len(run_prefix) :] in self.runs:
            run = self.path[len(run_prefix) :]
            items = [{"traceId": t} for t in self.runs[run]]
            body = json.dumps(
                {"id": f"run-{run}", "name": run, "createdAt": "2026-09-14T17:00:00Z", "datasetRunItems": items}
            )
            body = body.encode()
            self.send_response(200)
        else:
            body = b"{}"
            self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def langfuse_stub():
    server = HTTPServer(("127.0.0.1", 0), LangfuseStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """A repository on a feature branch with one source change and no tests."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "Tester")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n")
    (tmp_path / "mergeproof.yaml").write_text(
        "rules:\n"
        "  - id: src-needs-tests\n"
        "    when: {paths: ['src/**']}\n"
        "    require:\n"
        "      - check: tests.changed\n"
        "        with: {any_of: ['tests/**']}\n"
        "      - check: evidence.field\n"
        "        with: {key: environment, equals: staging}\n"
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    git(tmp_path, "checkout", "-qb", "feature")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    git(tmp_path, "commit", "-qam", "fix: bump value")
    return tmp_path
