"""Speak MCP to `mergeproof mcp` over stdio, as a coding agent would."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp", reason="install mergeproof[mcp]")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

pytestmark = pytest.mark.integration


def payload(result):
    """Unwrap a tool result: structured content when the server sends it, else the text blocks."""
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured:
        return structured.get("result", structured) if isinstance(structured, dict) else structured
    texts = [block.text for block in result.content if hasattr(block, "text")]
    if len(texts) > 1:
        return [json.loads(t) for t in texts]
    try:
        return json.loads(texts[0])
    except (json.JSONDecodeError, IndexError):
        return texts[0] if texts else None


async def with_session(repo: Path, fn):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mergeproof", "mcp", "--policy", "mergeproof.yaml", "--root", ".", "--base", "main"],
        cwd=str(repo),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        return await fn(session)


@pytest.mark.anyio
async def test_tools_are_listed_and_explain_works(sample_repo: Path):
    async def scenario(session):
        tools = {t.name for t in (await session.list_tools()).tools}
        assert {"explain", "check", "evidence_block", "validate_policy", "list_checks", "agent_instructions"} <= tools

        checks = payload(await session.call_tool("list_checks", {}))
        assert any(c["id"] == "review.human_verified" for c in checks)

        explained = payload(await session.call_tool("explain", {}))
        assert explained["verdict"] == "fail"
        assert "src-needs-tests" in explained["markdown"]
        assert explained["evidence_template"] == {"environment": "staging"}

        block = payload(await session.call_tool("evidence_block", {"data": {"environment": "staging"}}))
        assert block.strip() == "```evidence\nenvironment: staging\n```"

        checked = payload(await session.call_tool("check", {"pr_body": block}))
        assert checked["verdict"] == "fail" and checked["exit_code"] == 1

        valid = payload(
            await session.call_tool("validate_policy", {"text": "rules:\n  - id: a\n    require: [{check: nope}]\n"})
        )
        assert valid["ok"] is False and "unknown check" in valid["problems"][0]

        resources = {str(r.uri) for r in (await session.list_resources()).resources}
        assert "mergeproof://policy" in resources
        return True

    assert await with_session(sample_repo, scenario)


@pytest.fixture
def anyio_backend():
    return "asyncio"
