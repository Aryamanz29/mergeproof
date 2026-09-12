"""`mergeproof serve` starts, answers health checks, and refuses unsigned webhooks."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

pytest.importorskip("starlette", reason="install mergeproof[app]")
cryptography = pytest.importorskip("cryptography")

pytestmark = pytest.mark.integration


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_serve_starts_and_guards_the_webhook(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    (tmp_path / "key.pem").write_bytes(pem)
    port = free_port()
    env = os.environ | {
        "MERGEPROOF_APP_ID": "1",
        "MERGEPROOF_APP_PRIVATE_KEY_FILE": str(tmp_path / "key.pem"),
        "MERGEPROOF_WEBHOOK_SECRET": "s",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "mergeproof", "serve", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise AssertionError("server did not come up:\n" + (proc.stdout.read() if proc.stdout else ""))
        assert httpx.get(f"{base}/healthz").json()["ok"] is True
        assert httpx.post(f"{base}/webhook", content=b"{}").status_code == 401
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_serve_without_configuration_exits_with_usage_error():
    env = {k: v for k, v in os.environ.items() if not k.startswith("MERGEPROOF_")}
    proc = subprocess.run([sys.executable, "-m", "mergeproof", "serve"], env=env, capture_output=True, text=True)
    assert proc.returncode == 3 and "MERGEPROOF_APP_ID" in proc.stderr
