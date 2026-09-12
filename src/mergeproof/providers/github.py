"""Build a :class:`Context` from the GitHub REST API and publish reports back."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from mergeproof.context import ChangedFile, CheckRun, Comment, Context, ContextError
from mergeproof.report import Annotation, Status

API_URL = "https://api.github.com"


class Client:
    def __init__(self, token: str, api_url: str = API_URL, timeout: float = 30.0) -> None:
        self._http = httpx.Client(
            base_url=api_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "mergeproof",
            },
        )

    def get(self, path: str, **params: Any) -> Any:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def paginate(self, path: str, key: str | None = None) -> list[Any]:
        items: list[Any] = []
        page = 1
        while True:
            data = self.get(path, per_page=100, page=page)
            batch = data[key] if key else data
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self._http.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def patch(self, path: str, payload: dict[str, Any]) -> Any:
        response = self._http.patch(path, json=payload)
        response.raise_for_status()
        return response.json()


def client_from_env() -> Client:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise ContextError("GITHUB_TOKEN is required for GitHub mode")
    return Client(token, os.environ.get("GITHUB_API_URL", API_URL))


def locate_pr() -> tuple[str, int]:
    """Work out repo and PR number from the Actions event payload or MERGEPROOF_* variables."""
    repo = os.environ.get("MERGEPROOF_REPO") or os.environ.get("GITHUB_REPOSITORY")
    number = os.environ.get("MERGEPROOF_PR_NUMBER")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not number and event_path and os.path.exists(event_path):
        with open(event_path, encoding="utf-8") as fh:
            event = json.load(fh)
        pr = event.get("pull_request") or event.get("issue") or {}
        number = pr.get("number")
        repo = (event.get("repository") or {}).get("full_name") or repo
    if not repo or not number:
        raise ContextError("cannot locate the pull request: set MERGEPROOF_REPO and MERGEPROOF_PR_NUMBER")
    return repo, int(number)


def fetch(client: Client, repo: str, number: int, root: str = ".") -> Context:
    pr = client.get(f"/repos/{repo}/pulls/{number}")
    files = [
        ChangedFile(path=f["filename"], status=f["status"], previous_path=f.get("previous_filename"))
        for f in client.paginate(f"/repos/{repo}/pulls/{number}/files")
    ]
    comments = [
        Comment(
            author=c["user"]["login"],
            body=c.get("body") or "",
            created_at=c.get("created_at", ""),
            url=c.get("html_url"),
        )
        for c in client.paginate(f"/repos/{repo}/issues/{number}/comments")
    ]
    comments += [
        Comment(
            author=r["user"]["login"],
            body=r.get("body") or "",
            created_at=r.get("submitted_at", ""),
            kind="review",
            state=r.get("state"),
            url=r.get("html_url"),
        )
        for r in client.paginate(f"/repos/{repo}/pulls/{number}/reviews")
    ]
    comments += [
        Comment(
            author=c["user"]["login"],
            body=c.get("body") or "",
            created_at=c.get("created_at", ""),
            kind="review_comment",
            url=c.get("html_url"),
        )
        for c in client.paginate(f"/repos/{repo}/pulls/{number}/comments")
    ]
    head_sha = pr["head"]["sha"]
    check_runs = [
        CheckRun(name=r["name"], status=r["status"], conclusion=r.get("conclusion"), url=r.get("html_url"))
        for r in client.paginate(f"/repos/{repo}/commits/{head_sha}/check-runs", key="check_runs")
    ]
    return Context(
        source="github",
        online=True,
        repo=repo,
        number=number,
        title=pr.get("title") or "",
        body=pr.get("body") or "",
        author=(pr.get("user") or {}).get("login", ""),
        labels=[label["name"] for label in pr.get("labels", [])],
        base_ref=pr["base"]["ref"],
        head_sha=head_sha,
        base_sha=pr["base"]["sha"],
        root=root,
        files=files,
        comments=comments,
        check_runs=check_runs,
    )


def upsert_comment(client: Client, repo: str, number: int, body: str, marker: str) -> str:
    """Create or update the single comment carrying *marker*; return its URL."""
    for comment in client.paginate(f"/repos/{repo}/issues/{number}/comments"):
        if marker in (comment.get("body") or ""):
            client.patch(f"/repos/{repo}/issues/comments/{comment['id']}", {"body": body})
            return str(comment.get("html_url", ""))
    created = client.post(f"/repos/{repo}/issues/{number}/comments", {"body": body})
    return str(created.get("html_url", ""))


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


STATUS_STATE = {Status.PASS: "success", Status.WARN: "success", Status.PENDING: "pending", Status.FAIL: "failure"}
CHECK_CONCLUSION = {
    Status.PASS: "success",
    Status.WARN: "neutral",
    Status.PENDING: "action_required",
    Status.FAIL: "failure",
}


def set_commit_status(
    client: Client, repo: str, sha: str, verdict: Status, description: str, target_url: str | None
) -> None:
    """The line in the merge box. Requireable in branch protection under the context `mergeproof`."""
    payload: dict[str, Any] = {
        "state": STATUS_STATE[verdict],
        "context": "mergeproof",
        "description": description[:140],
    }
    if target_url:
        payload["target_url"] = target_url
    client.post(f"/repos/{repo}/statuses/{sha}", payload)


def create_check_run(
    client: Client,
    repo: str,
    sha: str,
    verdict: Status,
    title: str,
    summary: str,
    annotations: list[Annotation],
    details_url: str | None = None,
) -> str:
    """A Check Run with file annotations, shown in the Checks tab and inline in the diff."""
    payload: dict[str, Any] = {
        "name": "mergeproof",
        "head_sha": sha,
        "status": "completed",
        "conclusion": CHECK_CONCLUSION[verdict],
        "output": {
            "title": title[:255],
            "summary": summary[:65535],
            "annotations": [
                {
                    "path": a.path,
                    "start_line": a.line,
                    "end_line": a.line,
                    "annotation_level": "failure" if verdict == Status.FAIL else "warning",
                    "message": a.message[:64000],
                }
                for a in annotations[:50]
            ],
        },
    }
    if details_url:
        payload["details_url"] = details_url
    created = client.post(f"/repos/{repo}/check-runs", payload)
    return str(created.get("html_url", ""))


def run_url() -> str | None:
    server, repo, run_id = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else None
