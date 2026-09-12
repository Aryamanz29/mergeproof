"""Serve the policy to coding agents over the Model Context Protocol.

Every tool is read-only from the repository's point of view: agents learn
what a change must prove, check their work before pushing, and format the
evidence block. Nothing here can approve anything.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from mergeproof import __version__, engine, evidence, policy, render
from mergeproof.checks.registry import load_registry
from mergeproof.context import ContextError
from mergeproof.providers import git

INSTRUCTIONS = """\
mergeproof gates pull requests on evidence. Call `explain` before opening or updating a PR,
produce every artifact it lists, and use `evidence_block` to format what goes into the PR
description. Never fabricate evidence; leave a field out and say why. Human verification
cannot be produced by you."""


def build_server(policy_path: str = "mergeproof.yaml", root: str = ".", base: str = "origin/main") -> MCPServer:
    server = MCPServer(name="mergeproof", version=__version__, instructions=INSTRUCTIONS)
    registry = load_registry()

    def current_policy() -> policy.Policy:
        return policy.load(policy_path)

    def evaluate(body: str | None, title: str | None) -> tuple[policy.Policy, Any]:
        pol = current_policy()
        ctx = git.from_git(base=base, root=root, body=body, title=title)
        return pol, engine.evaluate(pol, ctx, registry)

    @server.tool(description="What the current diff must prove, what is already satisfied, and what is missing.")
    def explain(pr_body: str | None = None, pr_title: str | None = None) -> dict[str, Any]:
        try:
            pol, report = evaluate(pr_body, pr_title)
        except (policy.PolicyError, ContextError) as exc:
            return {"error": str(exc)}
        from mergeproof.cli import explanations

        return {
            "verdict": report.verdict.value,
            "markdown": render.explain_markdown(report, pol, explanations(pol, registry)),
            "evidence_template": report.evidence_template(),
        }

    @server.tool(description="Run the gate locally against the working tree; returns the JSON report and exit code.")
    def check(pr_body: str | None = None, pr_title: str | None = None) -> dict[str, Any]:
        try:
            _, report = evaluate(pr_body, pr_title)
        except (policy.PolicyError, ContextError) as exc:
            return {"error": str(exc)}
        return {
            "verdict": report.verdict.value,
            "exit_code": report.exit_code,
            "report": report.model_dump(mode="json"),
        }

    @server.tool(description="Format evidence data as the fenced block to paste into the PR description.")
    def evidence_block(data: dict[str, Any]) -> str:
        tag = current_policy().evidence_block
        return evidence.render(data, tag)

    @server.tool(description="Validate policy YAML text, or the repository policy when no text is given.")
    def validate_policy(text: str | None = None) -> dict[str, Any]:
        try:
            pol = policy.loads(text) if text else current_policy()
        except policy.PolicyError as exc:
            return {"ok": False, "problems": [str(exc)]}
        problems = policy.problems(pol, registry)
        return {"ok": not problems, "problems": problems, "rules": [r.id for r in pol.rules]}

    @server.tool(description="List available checks with their parameters, for writing or editing a policy.")
    def list_checks() -> list[dict[str, Any]]:
        return [
            {
                "id": check_id,
                "description": cls.description,
                "params": cls.Params.model_json_schema().get("properties", {}),
            }
            for check_id, cls in registry.items()
        ]

    @server.tool(description="The policy rendered as instructions for agents (same text as `mergeproof agent-prompt`).")
    def agent_instructions() -> str:
        return render.agent_prompt(current_policy(), registry)

    @server.resource(
        "mergeproof://policy", description="The repository's mergeproof policy file", mime_type="text/yaml"
    )
    def policy_resource() -> str:
        with open(policy_path, encoding="utf-8") as fh:
            return fh.read()

    return server


def serve(policy_path: str = "mergeproof.yaml", root: str = ".", base: str = "origin/main") -> None:
    build_server(policy_path, root, base).run("stdio")
