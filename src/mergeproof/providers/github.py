"""Build a :class:`Context` from the GitHub REST API and publish reports back."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from mergeproof.context import ChangedFile, CheckRun, Comment, Context, ContextError
from mergeproof.report import Annotation, Report, Status

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

    def delete(self, path: str) -> None:
        response = self._http.delete(path)
        response.raise_for_status()


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
    tree_data = client.get(f"/repos/{repo}/git/trees/{head_sha}", recursive="1")
    tree = (
        None
        if tree_data.get("truncated")
        else [e["path"] for e in tree_data.get("tree", []) if e.get("type") == "blob"]
    )
    check_runs = [
        CheckRun(
            name=r["name"],
            status=r["status"],
            conclusion=r.get("conclusion"),
            url=r.get("html_url"),
            started_at=r.get("started_at") or "",
        )
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
        tree=tree,
    )


def upsert_comment(client: Client, repo: str, number: int, body: str, marker: str, create: bool = True) -> str:
    """Create or update the single comment carrying *marker*; return its URL.

    With ``create=False`` an existing comment is updated but no new one is posted, which keeps
    pull requests that no rule applies to free of noise.
    """
    for comment in client.paginate(f"/repos/{repo}/issues/{number}/comments"):
        if marker in (comment.get("body") or ""):
            client.patch(f"/repos/{repo}/issues/comments/{comment['id']}", {"body": body})
            return str(comment.get("html_url", ""))
    if not create:
        return ""
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
MARK = "🛡️"


def titled(text: str) -> str:
    """The headline on the Check Run row, carrying the mark whatever token posted it.

    Only the Check Run gets it: the commit status API rejects descriptions containing emoji.
    """
    return f"{MARK} {text}"


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
            "title": titled(title)[:255],
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


REVIEW_MARKER = "<!-- mergeproof-review:{key} -->"


def review_comment_bodies(report: Report, cap: int = 20) -> dict[tuple[str, str], str]:
    """File-level review comments for what is still needed, keyed by (path, key).

    A finding that names a file (a missing test for it) goes on that file. A requirement that
    applies to the whole change goes on the first file that made its rule apply, once per rule,
    so the reader sees it where they are looking.
    """
    from mergeproof.policy import Severity

    bodies: dict[tuple[str, str], str] = {}
    for rule, req in report.blocking_unmet():
        if req.effective == Status.PENDING and not req.outcome.fix:
            continue
        strength = "blocking" if req.severity == Severity.BLOCK else "warning"
        heading = f"**mergeproof · {req.label}** <sub>rule `{rule.id}`, {strength}</sub>"
        fix = req.outcome.fix or req.outcome.summary
        note = f"\n\n<sub>{rule.instructions.strip()}</sub>" if rule.instructions else ""
        if req.outcome.annotations:
            for ann in req.outcome.annotations:
                key = f"{rule.id}:{req.label}:{ann.path}"
                bodies[(ann.path, key)] = f"{REVIEW_MARKER.format(key=key)}\n{heading}\n\n{ann.message}\n\n{fix}{note}"
        elif rule.files:
            key = f"{rule.id}:{req.label}"
            files = ", ".join(f"`{f}`" for f in rule.files[:3]) + (
                f" and {len(rule.files) - 3} more" if len(rule.files) > 3 else ""
            )
            why = f"This rule applies because the change touches {files}."
            body = f"{REVIEW_MARKER.format(key=key)}\n{heading}\n\n{req.outcome.summary}. {why}\n\n{fix}{note}"
            bodies[(rule.files[0], key)] = body
        if len(bodies) >= cap:
            break
    return bodies


def sync_review_comments(client: Client, report: Report, bodies: dict[tuple[str, str], str]) -> dict[str, int]:
    """Create, update or delete mergeproof's file-level review comments so they mirror *bodies*."""
    assert report.repo and report.number is not None and report.head_sha
    existing: dict[str, dict[str, Any]] = {}
    for comment in client.paginate(f"/repos/{report.repo}/pulls/{report.number}/comments"):
        text = comment.get("body") or ""
        if "<!-- mergeproof-review:" in text:
            key = text.split("<!-- mergeproof-review:", 1)[1].split(" -->", 1)[0]
            existing[key] = comment
    counts = {"created": 0, "updated": 0, "deleted": 0}
    wanted = {key: (path, body) for (path, key), body in bodies.items()}
    for key, (path, body) in wanted.items():
        current = existing.pop(key, None)
        if current is None:
            client.post(
                f"/repos/{report.repo}/pulls/{report.number}/comments",
                {"body": body, "commit_id": report.head_sha, "path": path, "subject_type": "file"},
            )
            counts["created"] += 1
        elif current.get("body") != body:
            client.patch(f"/repos/{report.repo}/pulls/comments/{current['id']}", {"body": body})
            counts["updated"] += 1
    for stale in existing.values():
        client.delete(f"/repos/{report.repo}/pulls/comments/{stale['id']}")
        counts["deleted"] += 1
    return counts
