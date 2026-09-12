"""Publish a report back to GitHub: upsert one sticky PR comment and write the step summary."""

from __future__ import annotations

import os

from ..context import GitHubAPI
from .markdown import MARKER


def upsert_comment(api: GitHubAPI, repo: str, number: int, body: str) -> str:
    for c in api.paginate(f"/repos/{repo}/issues/{number}/comments"):
        if MARKER in (c.get("body") or ""):
            api.patch(f"/repos/{repo}/issues/comments/{c['id']}", {"body": body})
            return c.get("html_url", "")
    created = api.post(f"/repos/{repo}/issues/{number}/comments", {"body": body})
    return created.get("html_url", "")


def write_step_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


def write_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")
