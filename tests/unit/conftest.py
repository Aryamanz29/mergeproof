from __future__ import annotations

from typing import Any

import pytest

from mergeproof.checks.base import Check
from mergeproof.checks.registry import builtin_registry
from mergeproof.context import ChangedFile, CheckRun, Comment, Context
from mergeproof.report import Outcome

HEAD = "abc1234def5678"


def make_context(
    files: list[str] | None = None,
    body: str = "",
    comments: list[Comment] | None = None,
    check_runs: list[CheckRun] | None = None,
    online: bool = True,
    **overrides: Any,
) -> Context:
    fields: dict[str, Any] = {
        "source": "github" if online else "local",
        "online": online,
        "title": "fix: something",
        "author": "octocat",
        "head_sha": HEAD,
        "body": body,
        "files": [ChangedFile(path=p) for p in files or []],
        "comments": comments or [],
        "check_runs": check_runs or [],
    }
    fields.update(overrides)
    return Context(**fields)


def run_check(check: Check, ctx: Context, files: list[str] | None = None, **params: Any) -> Outcome:
    parsed = check.parse_params(params)
    return check.run(ctx, parsed, ctx.changed_paths if files is None else files)


@pytest.fixture
def registry():
    return builtin_registry()


@pytest.fixture
def evidence_body():
    def build(**data: Any) -> str:
        import yaml

        return "## Summary\n\n```evidence\n" + yaml.safe_dump(data, sort_keys=False) + "```\n"

    return build
