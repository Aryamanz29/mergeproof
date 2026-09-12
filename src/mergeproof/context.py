"""Everything a check may inspect about a pull request.

Two providers share one interface:

* ``LocalContext``  - built from ``git`` (and optionally ``gh``) so agents and humans can run the
                      gate *before* pushing. Anything that needs the GitHub API reports PENDING.
* ``GitHubContext`` - built from the GitHub REST API inside Actions.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from typing import Any

import httpx

from .evidence import Evidence, parse_evidence


@dataclass
class ChangedFile:
    path: str
    status: str = "modified"  # added | modified | removed | renamed
    previous_path: str | None = None


@dataclass
class Comment:
    author: str
    body: str
    created_at: str = ""
    kind: str = "comment"  # comment | review | review_comment
    state: str | None = None  # APPROVED / CHANGES_REQUESTED / COMMENTED for reviews
    url: str | None = None

    @property
    def is_bot(self) -> bool:
        return self.author.endswith("[bot]")


@dataclass
class CheckRun:
    name: str
    status: str  # queued | in_progress | completed
    conclusion: str | None = None  # success | failure | neutral | cancelled | skipped | timed_out
    url: str | None = None


@dataclass
class PRContext:
    title: str = ""
    body: str = ""
    author: str = ""
    labels: list[str] = field(default_factory=list)
    base_ref: str = "main"
    head_sha: str | None = None
    base_sha: str | None = None
    repo: str | None = None
    number: int | None = None
    changed_files: list[ChangedFile] = field(default_factory=list)
    root: str = "."
    online: bool = False  # GitHub-API-backed data (comments, check runs) available?
    mode: str = "local"

    @property
    def changed_paths(self) -> list[str]:
        return [f.path for f in self.changed_files if f.status != "removed"]

    @property
    def head_short(self) -> str:
        return (self.head_sha or "")[:7]

    def comments(self) -> list[Comment]:
        return []

    def check_runs(self) -> list[CheckRun]:
        return []

    def base_commit_time(self) -> datetime | None:
        return None

    def evidence(self, tag: str = "evidence") -> Evidence:
        cache = self.__dict__.setdefault("_evidence_cache", {})
        if tag not in cache:
            cache[tag] = parse_evidence(self.body, tag)
        return cache[tag]


# --------------------------------------------------------------------------------------
# Local (git / gh) provider
# --------------------------------------------------------------------------------------


class ContextError(RuntimeError):
    """Raised when a PR context cannot be built (bad git ref, missing token, ...)."""


def _git(root: str, *args: str) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise ContextError("git is not installed") from None
    except subprocess.CalledProcessError as exc:
        raise ContextError(f"git {' '.join(args)}: {exc.stderr.strip() or exc.stdout.strip()}") from None
    return proc.stdout.strip()


_STATUS_MAP = {"A": "added", "M": "modified", "D": "removed", "R": "renamed", "C": "added", "T": "modified"}


def _parse_name_status(out: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0][0]
        status = _STATUS_MAP.get(code, "modified")
        if status == "renamed" and len(parts) >= 3:
            files.append(ChangedFile(parts[2], "renamed", previous_path=parts[1]))
        else:
            files.append(ChangedFile(parts[-1], status))
    return files


class LocalContext(PRContext):
    """Diff of the working tree (including uncommitted + untracked files) against a base ref."""

    @classmethod
    def from_git(
        cls,
        base: str = "origin/main",
        root: str = ".",
        body: str | None = None,
        title: str | None = None,
        use_gh: bool = False,
    ) -> LocalContext:
        merge_base = _git(root, "merge-base", base, "HEAD")
        files = _parse_name_status(_git(root, "diff", "--name-status", "-M", merge_base))
        seen = {f.path for f in files}
        for p in _git(root, "ls-files", "--others", "--exclude-standard").splitlines():
            if p and p not in seen:
                files.append(ChangedFile(p, "added"))
        ctx = cls(
            title=title or _git(root, "log", "-1", "--format=%s"),
            body=body or "",
            author=_git(root, "config", "user.name") if _has_config(root) else "",
            base_ref=base.split("/", 1)[-1],
            head_sha=_git(root, "rev-parse", "HEAD"),
            base_sha=merge_base,
            changed_files=files,
            root=root,
            online=False,
            mode="local",
        )
        if use_gh:
            ctx._hydrate_from_gh()
        return ctx

    def _hydrate_from_gh(self) -> None:
        if not shutil.which("gh"):
            return
        try:
            out = subprocess.run(
                ["gh", "pr", "view", "--json", "number,title,body,labels,author,baseRefName,url"],
                cwd=self.root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        except subprocess.CalledProcessError:
            return
        data = json.loads(out)
        self.number = data.get("number")
        self.title = data.get("title") or self.title
        self.body = data.get("body") or self.body
        self.labels = [lbl["name"] for lbl in data.get("labels", [])]
        self.author = (data.get("author") or {}).get("login", self.author)
        self.base_ref = data.get("baseRefName") or self.base_ref
        url = data.get("url") or ""
        if "github.com/" in url:
            self.repo = "/".join(url.split("github.com/")[1].split("/")[:2])
        self.__dict__.pop("_evidence_cache", None)


def _has_config(root: str) -> bool:
    try:
        _git(root, "config", "user.name")
        return True
    except subprocess.CalledProcessError:
        return False


# --------------------------------------------------------------------------------------
# GitHub provider
# --------------------------------------------------------------------------------------


class GitHubAPI:
    def __init__(self, token: str, api_url: str = "https://api.github.com", timeout: float = 30.0):
        self._client = httpx.Client(
            base_url=api_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "mergeproof",
            },
            timeout=timeout,
        )

    def get(self, path: str, **params: Any) -> Any:
        r = self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def paginate(self, path: str, key: str | None = None, **params: Any) -> list[Any]:
        items: list[Any] = []
        page = 1
        while True:
            data = self.get(path, per_page=100, page=page, **params)
            batch = data[key] if key else data
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        r = self._client.post(path, json=payload)
        r.raise_for_status()
        return r.json()

    def patch(self, path: str, payload: dict[str, Any]) -> Any:
        r = self._client.patch(path, json=payload)
        r.raise_for_status()
        return r.json()


class GitHubContext(PRContext):
    api: GitHubAPI | None = None

    @classmethod
    def from_env(cls, api: GitHubAPI | None = None, root: str = ".") -> GitHubContext:
        """Resolve repo + PR number from the Actions event payload."""
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        repo = os.environ.get("GITHUB_REPOSITORY")
        number: int | None = None
        if event_path and os.path.exists(event_path):
            with open(event_path, encoding="utf-8") as fh:
                event = json.load(fh)
            pr = event.get("pull_request") or event.get("issue") or {}
            number = pr.get("number")
            repo = (event.get("repository") or {}).get("full_name", repo)
        if os.environ.get("MERGEPROOF_PR_NUMBER"):
            number = int(os.environ["MERGEPROOF_PR_NUMBER"])
        if not repo or number is None:
            raise RuntimeError(
                "cannot determine repo/PR: run on a pull_request event or set GITHUB_REPOSITORY + MERGEPROOF_PR_NUMBER"
            )
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if api is None:
            if not token:
                raise ContextError("GITHUB_TOKEN is required for --github mode")
            api = GitHubAPI(token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))
        return cls.fetch(api, repo, number, root=root)

    @classmethod
    def fetch(cls, api: GitHubAPI, repo: str, number: int, root: str = ".") -> GitHubContext:
        pr = api.get(f"/repos/{repo}/pulls/{number}")
        files = [
            ChangedFile(f["filename"], f["status"], f.get("previous_filename"))
            for f in api.paginate(f"/repos/{repo}/pulls/{number}/files")
        ]
        ctx = cls(
            title=pr.get("title") or "",
            body=pr.get("body") or "",
            author=(pr.get("user") or {}).get("login", ""),
            labels=[lbl["name"] for lbl in pr.get("labels", [])],
            base_ref=pr["base"]["ref"],
            head_sha=pr["head"]["sha"],
            base_sha=pr["base"]["sha"],
            repo=repo,
            number=number,
            changed_files=files,
            root=root,
            online=True,
            mode="github",
        )
        ctx.api = api
        return ctx

    @cached_property
    def _comments(self) -> list[Comment]:
        assert self.api and self.repo and self.number is not None
        out: list[Comment] = []
        for c in self.api.paginate(f"/repos/{self.repo}/issues/{self.number}/comments"):
            out.append(
                Comment(
                    c["user"]["login"], c.get("body") or "", c.get("created_at", ""), "comment", None, c.get("html_url")
                )
            )
        for r in self.api.paginate(f"/repos/{self.repo}/pulls/{self.number}/reviews"):
            out.append(
                Comment(
                    r["user"]["login"],
                    r.get("body") or "",
                    r.get("submitted_at", ""),
                    "review",
                    r.get("state"),
                    r.get("html_url"),
                )
            )
        for c in self.api.paginate(f"/repos/{self.repo}/pulls/{self.number}/comments"):
            out.append(
                Comment(
                    c["user"]["login"],
                    c.get("body") or "",
                    c.get("created_at", ""),
                    "review_comment",
                    None,
                    c.get("html_url"),
                )
            )
        return out

    def comments(self) -> list[Comment]:
        return self._comments

    @cached_property
    def _check_runs(self) -> list[CheckRun]:
        assert self.api and self.repo and self.head_sha
        runs = self.api.paginate(f"/repos/{self.repo}/commits/{self.head_sha}/check-runs", key="check_runs")
        return [CheckRun(r["name"], r["status"], r.get("conclusion"), r.get("html_url")) for r in runs]

    def check_runs(self) -> list[CheckRun]:
        return self._check_runs

    def base_commit_time(self) -> datetime | None:
        if not (self.api and self.repo and self.base_sha):
            return None
        data = self.api.get(f"/repos/{self.repo}/commits/{self.base_sha}")
        stamp = data["commit"]["committer"]["date"]
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
