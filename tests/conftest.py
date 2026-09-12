from __future__ import annotations

import pytest

from mergeproof.context import ChangedFile, CheckRun, Comment, PRContext


class FakeContext(PRContext):
    """In-memory PR for tests; behaves like GitHub mode when `online=True`."""

    def __init__(self, files=(), body="", comments=(), check_runs=(), online=True, **kw):
        kw.setdefault("title", "fix: something")
        kw.setdefault("author", "octocat")
        kw.setdefault("head_sha", "abc1234def5678")
        kw.setdefault("mode", "github" if online else "local")
        super().__init__(
            body=body,
            changed_files=[ChangedFile(f) if isinstance(f, str) else f for f in files],
            online=online,
            **kw,
        )
        self._c = list(comments)
        self._r = list(check_runs)

    def comments(self):
        return self._c

    def check_runs(self):
        return self._r


@pytest.fixture
def ctx_factory():
    return FakeContext


BT = "https://www.braintrust.dev/app/acme/p/mcp-internal/logs?r="


@pytest.fixture
def bt_url():
    return BT


__all__ = ["FakeContext", "Comment", "CheckRun", "ChangedFile"]
