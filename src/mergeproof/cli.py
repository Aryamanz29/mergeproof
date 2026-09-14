"""Command line interface.

Porcelain commands do the whole job in one go::

    mergeproof check            evaluate the policy, print a report, exit 0/1/2
    mergeproof explain          what must this diff prove, what is missing right now

Plumbing commands are filters that read and write JSON so they can be piped::

    mergeproof context --github | mergeproof check --context - --format json | mergeproof report --format md

Exit codes: 0 pass or warn, 1 fail, 2 pending, 3 usage or policy error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import NoReturn

import httpx

from mergeproof import __version__, engine, evidence, policy, receipt, render
from mergeproof.checks.registry import Registry, load_registry
from mergeproof.context import Context, ContextError
from mergeproof.providers import git, github
from mergeproof.report import EXIT_USAGE, Report

DEFAULT_POLICY = "mergeproof.yaml"

STARTER_POLICY = """\
# What a change must prove before it merges. Docs: https://github.com/Aryamanz29/mergeproof
version: 1
project: my-project

rules:
  - id: source-change-needs-tests
    description: Source changes ship with tests for the touched module.
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
        name: tests green
        with: { name: "test", regex: true }

  - id: fix-needs-live-evidence
    description: Bug fixes show the behaviour before and after on a live environment.
    when:
      title: "^fix"
    instructions: >
      Reproduce the bug on staging and keep the link, deploy the fix, repeat the same
      steps and keep that link too. A reviewer opens both and posts `/verified <sha7>`.
    require:
      - check: evidence.field
        name: environment
        with: { key: environment, equals: staging }
      - check: evidence.links
        name: before/after links
        with: { min_pairs: 1 }
      - check: review.human_verified
        name: reviewer verified
"""


def die(message: str, code: int = EXIT_USAGE) -> NoReturn:
    print(f"mergeproof: {message}", file=sys.stderr)
    sys.exit(code)


def add_policy_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-p", "--policy", default=os.environ.get("MERGEPROOF_POLICY", DEFAULT_POLICY), help="policy file"
    )


def add_context_args(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--context", metavar="FILE", help="read a context JSON produced by `mergeproof context` ('-' for stdin)"
    )
    source.add_argument(
        "--github", action="store_true", help="fetch the PR through the GitHub API (needs GITHUB_TOKEN)"
    )
    source.add_argument("--local", action="store_true", help="diff the working tree against --base (default)")
    parser.add_argument(
        "--base", default=os.environ.get("MERGEPROOF_BASE", "origin/main"), help="base ref for local mode"
    )
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--body-file", metavar="FILE", help="local mode: file holding the PR description")
    parser.add_argument("--title", help="local mode: PR title (default: last commit subject)")
    parser.add_argument("--gh", action="store_true", help="local mode: take title, body and labels from `gh pr view`")


def add_publish_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--comment", action="store_true", help="create or update the sticky PR comment")
    parser.add_argument(
        "--status", action="store_true", help="set the `mergeproof` commit status (needs statuses: write)"
    )
    parser.add_argument("--check-run", action="store_true", help=argparse.SUPPRESS)  # removed in 0.8
    parser.add_argument(
        "--review-comments", action="store_true", help="post what is needed as review comments on the files concerned"
    )
    parser.add_argument(
        "--receipt", action="store_true", help="when the pull request has merged, store the final report on a branch"
    )
    parser.add_argument("--receipt-branch", default=receipt.DEFAULT_BRANCH, metavar="BRANCH")


def build_context(args: argparse.Namespace) -> Context:
    try:
        if args.context:
            text = sys.stdin.read() if args.context == "-" else Path(args.context).read_text(encoding="utf-8")
            return Context.from_json(text)
        in_actions = os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_EVENT_PATH")
        if args.github or (not args.local and in_actions):
            repo, number = github.locate_pr()
            return github.fetch(github.client_from_env(), repo, number, root=args.root)
        body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else None
        ctx = git.from_git(base=args.base, root=args.root, body=body, title=args.title)
        return git.hydrate_from_gh(ctx) if args.gh else ctx
    except ContextError as exc:
        die(str(exc))
    except httpx.HTTPStatusError as exc:
        die(f"GitHub API returned {exc.response.status_code} for {exc.request.url.path}")
    except ValueError as exc:
        die(f"invalid context JSON: {exc}")


def load_policy(args: argparse.Namespace, registry: Registry) -> policy.Policy:
    try:
        loaded = policy.load(args.policy)
    except policy.PolicyError as exc:
        die(str(exc))
    problems = policy.problems(loaded, registry)
    if problems:
        die("invalid policy:\n  " + "\n  ".join(problems))
    return loaded


def emit(report: Report, fmt: str) -> str:
    if fmt == "json":
        return report.to_json()
    if fmt == "md":
        return render.report_markdown(report, marker=False)
    if fmt == "junit":
        return render.junit_xml(report)
    if fmt == "rdjson":
        return render.rdjson(report)
    return render.report_text(report)


def cmd_check(args: argparse.Namespace) -> int:
    registry = load_registry()
    pol = load_policy(args, registry)
    ctx = build_context(args)
    report = engine.evaluate(pol, ctx, registry)
    report.policy_path = args.policy
    report.policy_sha256 = policy_digest(args.policy)
    if args.output:
        Path(args.output).write_text(report.to_json(), encoding="utf-8")
    if not args.quiet:
        print(emit(report, args.format))
        if args.format == "text" and os.environ.get("GITHUB_ACTIONS") == "true":
            # Workflow commands ride along with the human output only; json, junit and rdjson stay clean.
            for line in render.workflow_commands(report):
                print(line)
    github.write_step_summary(render.report_markdown(report))
    github.write_output("verdict", report.verdict.value)
    if args.comment or args.status or args.review_comments or args.receipt:
        publish(
            report,
            comment=args.comment,
            status=args.status,
            review_comments=args.review_comments,
            receipt=args.receipt,
            receipt_branch=args.receipt_branch,
        )
    return report.exit_code


def publish(
    report: Report,
    comment: bool = True,
    status: bool = False,
    review_comments: bool = False,
    receipt: bool = False,
    receipt_branch: str = receipt.DEFAULT_BRANCH,
) -> None:
    """Report back to GitHub: the sticky comment, the commit status, review comments on files, the receipt."""
    if report.source != "github" or not report.repo or report.number is None or not report.head_sha:
        print("mergeproof: publishing needs a GitHub context; skipping", file=sys.stderr)
        return
    link = github.run_url()
    receipt_url: str | None = None
    try:
        client = github.client_from_env()
        if receipt and report.merged and report.merge_commit_sha:
            receipt_url = store_receipt(client, report, link, receipt_branch)
        if comment:
            url = github.upsert_comment(
                client,
                report.repo,
                report.number,
                render.report_markdown(report, run_url=link, receipt_url=receipt_url),
                render.MARKER,
                create=bool(report.matched),
            )
            link = url or link
            print(
                f"mergeproof: comment at {url}" if url else "mergeproof: no rules apply; no comment posted",
                file=sys.stderr,
            )
        if status:
            github.set_commit_status(client, report.repo, report.head_sha, report.verdict, report.headline(), link)
            print(f"mergeproof: commit status {github.STATUS_STATE[report.verdict]}", file=sys.stderr)
        if review_comments:
            counts = github.sync_review_comments(client, report, github.review_comment_bodies(report))
            summary = ", ".join(f"{n} {what}" for what, n in counts.items() if n) or "unchanged"
            print(f"mergeproof: review comments {summary}", file=sys.stderr)
    except (ContextError, httpx.HTTPError) as exc:
        die(f"could not publish the report: {exc}")


def store_receipt(client: github.Client, report: Report, run_url: str | None, branch: str) -> str | None:
    """Write the receipt; a missing permission is reported, not fatal, so the comment still lands."""
    assert report.repo
    try:
        url = receipt.write(client, report.repo, receipt.build(report, run_url), branch)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 404):
            print(
                f"mergeproof: could not write the receipt to {branch} ({exc.response.status_code});"
                " the workflow needs contents: write",
                file=sys.stderr,
            )
            return None
        raise
    github.write_output("receipt", url)
    print(f"mergeproof: receipt at {url}", file=sys.stderr)
    return url


def policy_digest(path: str) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def cmd_receipt(args: argparse.Namespace) -> int:
    repo = args.repo or os.environ.get("MERGEPROOF_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        die("which repository? pass --repo OWNER/NAME")
    try:
        doc = receipt.read(github.client_from_env(), repo, args.key, args.branch)
    except (LookupError, ContextError, httpx.HTTPError) as exc:
        die(str(exc), code=1)
    print(json.dumps(doc, indent=2) if args.json else receipt.summary(doc))
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    registry = load_registry()
    pol = load_policy(args, registry)
    ctx = build_context(args)
    report = engine.evaluate(pol, ctx, registry)
    if args.format == "json":
        print(report.to_json())
    elif args.format == "text":
        print(render.report_text(report, verbose=True))
    else:
        print(render.explain_markdown(report, pol, explanations(pol, registry)))
    return 0


def explanations(pol: policy.Policy, registry: Registry) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for rule in pol.rules:
        for req in rule.require:
            check = registry.lookup(req.check)
            if check is not None:
                out[(rule.id, req.label)] = check.explain(check.parse_params(req.params))
    return out


def cmd_context(args: argparse.Namespace) -> int:
    print(build_context(args).to_json())
    return 0


def read_report(source: str) -> Report:
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        return Report.from_json(text)
    except (OSError, ValueError) as exc:
        die(f"cannot read report: {exc}")


def cmd_report(args: argparse.Namespace) -> int:
    report = read_report(args.report)
    print(emit(report, args.format))
    return report.exit_code if args.exit_status else 0


def cmd_comment(args: argparse.Namespace) -> int:
    publish(
        read_report(args.report),
        comment=True,
        status=args.status,
        review_comments=args.review_comments,
        receipt=args.receipt,
        receipt_branch=args.receipt_branch,
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    load_policy(args, load_registry())
    print(f"{args.policy}: ok")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.policy)
    if target.exists() and not args.force:
        die(f"{target} exists; use --force to overwrite")
    target.write_text(STARTER_POLICY, encoding="utf-8")
    print(f"wrote {target}")
    return 0


def cmd_checks(args: argparse.Namespace) -> int:
    for check_id, cls in load_registry().items():
        print(check_id + ("  (GitHub mode only)" if cls.needs_github else ""))
        print(f"    {cls.description}")
        for name, field in cls.Params.model_fields.items():
            if field.is_required():
                default = ""
            elif field.default_factory is not None:
                default = f" (default {field.default_factory()!r})"  # type: ignore[call-arg]
            else:
                default = f" (default {field.default!r})"
            note = f": {field.description}" if field.description else ""
            print(f"      {name}{default}{note}")
    return 0


def cmd_agent_prompt(args: argparse.Namespace) -> int:
    registry = load_registry()
    print(render.agent_prompt(load_policy(args, registry), registry))
    return 0


def cmd_template(args: argparse.Namespace) -> int:
    registry = load_registry()
    pol = load_policy(args, registry)
    ctx = build_context(args)
    report = engine.evaluate(pol, ctx, registry)
    print(evidence.render(report.evidence_template(), pol.evidence_block) or "# nothing missing")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mergeproof", description="Evidence gates for pull requests.")
    parser.add_argument("--version", action="version", version=f"mergeproof {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("check", help="evaluate the policy and report; exit 0 pass, 1 fail, 2 pending")
    add_policy_arg(p)
    add_context_args(p)
    p.add_argument("-f", "--format", choices=render.FORMATS, default="text")
    p.add_argument("-o", "--output", metavar="FILE", help="also write the JSON report here")
    add_publish_args(p)
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("explain", help="what this change must prove and what is missing")
    add_policy_arg(p)
    add_context_args(p)
    p.add_argument("-f", "--format", choices=("text", "md", "json"), default="md")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("template", help="print the evidence block still missing for this change")
    add_policy_arg(p)
    add_context_args(p)
    p.set_defaults(func=cmd_template)

    p = sub.add_parser("context", help="print the pull request context as JSON")
    add_context_args(p)
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("report", help="render a JSON report in another format")
    p.add_argument("report", nargs="?", default="-", help="report file, or - for stdin")
    p.add_argument("-f", "--format", choices=render.FORMATS, default="text")
    p.add_argument("--exit-status", action="store_true", help="exit with the report's verdict code")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("comment", help="post a JSON report to the PR: sticky comment, optionally status")
    p.add_argument("report", nargs="?", default="-")
    p.add_argument("--status", action="store_true", help="also set the `mergeproof` commit status")
    p.add_argument("--check-run", action="store_true", help=argparse.SUPPRESS)  # removed in 0.8
    p.add_argument("--review-comments", action="store_true", help="also post review comments on the files concerned")
    p.add_argument("--receipt", action="store_true", help="when the PR has merged, store the final report on a branch")
    p.add_argument("--receipt-branch", default=receipt.DEFAULT_BRANCH, metavar="BRANCH")
    p.set_defaults(func=cmd_comment)

    p = sub.add_parser("receipt", help="show what a merged pull request proved (by merge sha, #number or number)")
    p.add_argument("key", help="merge commit sha, `#123` or `123`")
    p.add_argument("--repo", help="OWNER/NAME; default from MERGEPROOF_REPO or GITHUB_REPOSITORY")
    p.add_argument("--branch", default=receipt.DEFAULT_BRANCH, help="branch holding the receipts")
    p.add_argument("--json", action="store_true", help="print the whole receipt document")
    p.set_defaults(func=cmd_receipt)

    p = sub.add_parser("validate", help="check the policy file")
    add_policy_arg(p)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("init", help="write a starter policy")
    add_policy_arg(p)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("checks", help="list available checks and their parameters")
    p.set_defaults(func=cmd_checks)

    p = sub.add_parser("agent-prompt", help="render a CLAUDE.md / AGENTS.md section from the policy")
    add_policy_arg(p)
    p.set_defaults(func=cmd_agent_prompt)

    return parser


def main(argv: list[str] | None = None) -> NoReturn:
    args = build_parser().parse_args(argv)
    if getattr(args, "check_run", False):
        die("--check-run was removed in 0.8: require the `mergeproof` commit status instead (see the FAQ)")
    sys.exit(args.func(args))
