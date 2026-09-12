"""mergeproof command line."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

from . import __version__
from .checks.registry import default_registry
from .context import ContextError, GitHubContext, LocalContext, PRContext
from .engine import PolicyError, evaluate, load_policy, validate_policy
from .models import Status
from .render.github import upsert_comment, write_output, write_step_summary
from .render.markdown import render_agent_prompt, render_explain, render_report

DEFAULT_POLICY = "mergeproof.yaml"

STARTER_POLICY = """\
# mergeproof policy — declare what a change must prove.
# Docs: https://github.com/Aryamanz29/mergeproof
version: 1
project: my-project
evidence_block: evidence

rules:
  - id: source-change-needs-tests
    description: Source changes ship with unit tests for the touched module.
    when:
      paths: ["src/**/*.py"]
      exclude_paths: ["src/**/__init__.py"]
    require:
      - check: tests.changed
        name: unit tests touched
        with:
          map:
            "src/{pkg}/{name}.py": "tests/**/test_{name}*.py"
      - check: ci.job_passed
        name: unit tests green
        with: { name: "tests" }

  - id: bugfix-live-evidence
    description: Bug fixes prove the behaviour change on a live environment.
    when:
      title: "^fix"
    instructions: >
      Reproduce on the staging tenant, capture a trace, deploy the fix, repeat the same call and
      capture the after trace. A reviewer opens both links and posts `/verified <sha>`.
    require:
      - check: evidence.field
        name: tenant
        with: { key: tenant, equals: staging }
      - check: evidence.traces
        name: before/after traces
        with: { project: my-project, min_pairs: 1 }
      - check: review.human_verified
        name: reviewer verified traces
        with: { phrase: "/verified", bind_to_head: true }
"""


def _add_context_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--policy", "-p", default=DEFAULT_POLICY)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--github", action="store_true", help="Resolve the PR from the Actions event + GITHUB_TOKEN")
    mode.add_argument("--local", action="store_true", help="Diff the working tree against --base (default)")
    p.add_argument("--base", default=os.environ.get("MERGEPROOF_BASE", "origin/main"))
    p.add_argument("--root", default=".")
    p.add_argument("--body-file", help="Local mode: file containing the PR description")
    p.add_argument("--title", help="Local mode: PR title (default: last commit subject)")
    p.add_argument("--gh", action="store_true", help="Local mode: hydrate title/body/labels via `gh pr view`")


def _build_context(args: argparse.Namespace) -> PRContext:
    try:
        return _build_context_inner(args)
    except ContextError as exc:
        sys.exit(f"mergeproof: {exc}")
    except httpx.HTTPStatusError as exc:
        sys.exit(f"mergeproof: GitHub API {exc.response.status_code} for {exc.request.url.path}")


def _build_context_inner(args: argparse.Namespace) -> PRContext:
    if args.github or (
        not args.local and os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_EVENT_PATH")
    ):
        return GitHubContext.from_env(root=args.root)
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else None
    return LocalContext.from_git(base=args.base, root=args.root, body=body, title=args.title, use_gh=args.gh)


def _load(args: argparse.Namespace):
    try:
        policy = load_policy(args.policy)
    except FileNotFoundError:
        sys.exit(f"mergeproof: policy file {args.policy!r} not found (run `mergeproof init`)")
    except PolicyError as exc:
        sys.exit(f"mergeproof: {exc}")
    problems = validate_policy(policy)
    if problems:
        sys.exit("mergeproof: invalid policy:\n  " + "\n  ".join(problems))
    return policy


def cmd_check(args: argparse.Namespace) -> int:
    policy = _load(args)
    ctx = _build_context(args)
    report = evaluate(policy, ctx)
    md = render_report(report, policy.evidence_block)
    if args.json:
        Path(args.json).write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if not args.quiet:
        print(render_report(report, policy.evidence_block, include_marker=False))
    write_step_summary(md)
    write_output("verdict", report.verdict.value)
    if args.comment:
        if not isinstance(ctx, GitHubContext) or ctx.api is None:
            print("mergeproof: --comment needs GitHub mode; skipping", file=sys.stderr)
        else:
            url = upsert_comment(ctx.api, ctx.repo, ctx.number, md)  # type: ignore[arg-type]
            print(f"mergeproof: report posted {url}", file=sys.stderr)
    return _exit_code(report.verdict, args)


def _exit_code(verdict: Status, args: argparse.Namespace) -> int:
    if verdict == Status.FAIL:
        return 1
    if verdict == Status.PENDING:
        return 0 if args.pending_ok else 1
    if verdict == Status.WARN and args.fail_on == "warn":
        return 1
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    policy = _load(args)
    ctx = _build_context(args)
    report = evaluate(policy, ctx)
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    else:
        print(render_explain(report, policy))
    return 0


def cmd_agent_prompt(args: argparse.Namespace) -> int:
    policy = _load(args)
    print(render_agent_prompt(policy))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    _load(args)
    print(f"{args.policy}: OK")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.policy)
    if path.exists() and not args.force:
        sys.exit(f"mergeproof: {path} exists (use --force to overwrite)")
    path.write_text(STARTER_POLICY, encoding="utf-8")
    print(f"wrote {path}")
    return 0


def cmd_checks(_: argparse.Namespace) -> int:
    reg = default_registry()
    for cid, cls in sorted(reg.classes().items()):
        print(f"{cid}")
        print(f"    {cls.description}")
        for name, f in cls.Params.model_fields.items():
            default = "" if f.is_required() else f" (default: {f.default!r})"
            desc = f" — {f.description}" if f.description else ""
            print(f"      with.{name}{default}{desc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mergeproof", description="Evidence gates for pull requests.")
    p.add_argument("--version", action="version", version=f"mergeproof {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="Evaluate the policy and (in CI) post the report")
    _add_context_args(c)
    c.add_argument("--comment", action="store_true", help="Upsert the sticky PR comment (GitHub mode)")
    c.add_argument("--json", help="Write the machine-readable report here")
    c.add_argument("--quiet", "-q", action="store_true")
    c.add_argument("--pending-ok", action="store_true", help="Exit 0 while evidence is pending (default: exit 1)")
    c.add_argument("--fail-on", choices=["block", "warn"], default="block")
    c.set_defaults(func=cmd_check)

    e = sub.add_parser("explain", help="Show what the current diff must prove and what is missing")
    _add_context_args(e)
    e.add_argument("--format", choices=["md", "json"], default="md")
    e.set_defaults(func=cmd_explain)

    a = sub.add_parser("agent-prompt", help="Emit a CLAUDE.md/AGENTS.md section generated from the policy")
    a.add_argument("--policy", "-p", default=DEFAULT_POLICY)
    a.set_defaults(func=cmd_agent_prompt)

    v = sub.add_parser("validate", help="Validate the policy file")
    v.add_argument("--policy", "-p", default=DEFAULT_POLICY)
    v.set_defaults(func=cmd_validate)

    i = sub.add_parser("init", help="Write a starter policy")
    i.add_argument("--policy", "-p", default=DEFAULT_POLICY)
    i.add_argument("--force", action="store_true")
    i.set_defaults(func=cmd_init)

    k = sub.add_parser("checks", help="List available checks and their parameters")
    k.set_defaults(func=cmd_checks)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    main()
