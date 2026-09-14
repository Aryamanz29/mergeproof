"""Build a :class:`Context` from a local git checkout.

The diff is taken from the merge base with *base* to the working tree, so
uncommitted and untracked files count. That is what a contributor or an
agent wants to know before pushing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

from mergeproof.context import ChangedFile, Context, ContextError

STATUS = {"A": "added", "M": "modified", "D": "removed", "R": "renamed", "C": "added", "T": "modified"}


def git(root: str, *args: str) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise ContextError("git is not installed") from None
    except subprocess.CalledProcessError as exc:
        raise ContextError(f"git {' '.join(args)}: {(exc.stderr or exc.stdout).strip()}") from None
    return proc.stdout.strip()


def parse_name_status(output: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        status = STATUS.get(fields[0][0], "modified")
        if status == "renamed" and len(fields) >= 3:
            files.append(ChangedFile(path=fields[2], status=status, previous_path=fields[1]))
        else:
            files.append(ChangedFile(path=fields[-1], status=status))
    return files


def from_git(base: str = "origin/main", root: str = ".", body: str | None = None, title: str | None = None) -> Context:
    merge_base = git(root, "merge-base", base, "HEAD")
    files = parse_name_status(git(root, "diff", "--name-status", "-M", merge_base))
    known = {f.path for f in files}
    tracked = git(root, "ls-files").splitlines()
    untracked = [p for p in git(root, "ls-files", "--others", "--exclude-standard").splitlines() if p]
    for path in untracked:
        if path not in known:
            files.append(ChangedFile(path=path, status="added"))
    removed = {f.path for f in files if f.status == "removed"}
    return Context(
        source="local",
        online=False,
        title=title if title is not None else git(root, "log", "-1", "--format=%s"),
        body=body or "",
        author=_config(root, "user.name"),
        base_ref=base.split("/", 1)[-1],
        head_sha=git(root, "rev-parse", "HEAD"),
        base_sha=merge_base,
        root=root,
        files=files,
        tree=sorted((set(tracked) | set(untracked)) - removed),
    )


def hydrate_from_gh(ctx: Context) -> Context:
    """Fill title, body and labels from the open PR for this branch using the gh CLI, if available."""
    if not shutil.which("gh"):
        return ctx
    try:
        out = subprocess.run(
            ["gh", "pr", "view", "--json", "number,title,body,labels,author,baseRefName,url"],
            cwd=ctx.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError:
        return ctx
    data = json.loads(out)
    url = data.get("url") or ""
    repo = "/".join(url.split("github.com/")[1].split("/")[:2]) if "github.com/" in url else None
    return ctx.model_copy(
        update={
            "number": data.get("number"),
            "title": data.get("title") or ctx.title,
            "body": data.get("body") or ctx.body,
            "labels": [label["name"] for label in data.get("labels", [])],
            "author": (data.get("author") or {}).get("login", ctx.author),
            "base_ref": data.get("baseRefName") or ctx.base_ref,
            "repo": repo,
        }
    )


def _config(root: str, key: str) -> str:
    try:
        return git(root, "config", key)
    except ContextError:
        return ""


def remote_repo(root: str = ".", remote: str = "origin") -> str | None:
    """`OWNER/NAME` from the remote's URL, for GitHub remotes over https or ssh; None otherwise."""
    try:
        url = git(root, "remote", "get-url", remote).strip()
    except Exception:
        return None
    match = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", url)
    return match.group(1) if match else None
