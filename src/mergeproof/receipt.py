"""The receipt: what a pull request proved, written down when it merges.

The gate is a live evaluation. Comments get edited, trace links expire, people
leave. The receipt is the final report for the merged commit, stored as a JSON
file on a branch of the same repository, so "what proved this change?" has an
answer that needs no API and no third party.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from mergeproof import __version__
from mergeproof.providers.github import Client
from mergeproof.report import Report

DEFAULT_BRANCH = "mergeproof-receipts"


def path_for(merge_sha: str) -> str:
    return f"receipts/{merge_sha}.json"


def build(report: Report, run_url: str | None = None) -> dict[str, Any]:
    """The receipt document: the report plus what identifies the merge it belongs to."""
    return {
        "receipt": {
            "format": 1,
            "mergeproof": __version__,
            "repo": report.repo,
            "pull_request": report.number,
            "head_sha": report.head_sha,
            "merge_commit_sha": report.merge_commit_sha,
            "merged_at": report.merged_at,
            "merged_by": report.merged_by,
            "policy": report.policy_path,
            "policy_sha256": report.policy_sha256,
            "verdict": report.verdict.value,
            "headline": report.headline(),
            "evaluated_at": report.evaluated_at,
            "run_url": run_url,
        },
        "report": json.loads(report.to_json()),
    }


def write(client: Client, repo: str, doc: dict[str, Any], branch: str = DEFAULT_BRANCH) -> str:
    """Commit the receipt to *branch* through the git data API; no checkout needed.

    The branch is created as an orphan on first use. Returns the file's URL on GitHub.
    """
    merge_sha = doc["receipt"]["merge_commit_sha"]
    path = path_for(merge_sha)
    content = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    blob = client.post(f"/repos/{repo}/git/blobs", {"content": content, "encoding": "utf-8"})
    parents: list[str] = []
    tree_payload: dict[str, Any] = {"tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]}]}
    try:
        head = client.get(f"/repos/{repo}/git/ref/heads/{branch}")["object"]["sha"]
        parents = [head]
        tree_payload["base_tree"] = client.get(f"/repos/{repo}/git/commits/{head}")["tree"]["sha"]
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
    tree = client.post(f"/repos/{repo}/git/trees", tree_payload)
    number = doc["receipt"]["pull_request"]
    commit = client.post(
        f"/repos/{repo}/git/commits",
        {"message": f"receipt: #{number} merged as {merge_sha[:7]}", "tree": tree["sha"], "parents": parents},
    )
    if parents:
        client.patch(f"/repos/{repo}/git/refs/heads/{branch}", {"sha": commit["sha"], "force": False})
    else:
        client.post(f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    return f"https://github.com/{repo}/blob/{branch}/{path}"


def resolve(client: Client, repo: str, key: str) -> str:
    """A merge commit sha from a sha, a `#123` or a bare pull request number."""
    key = key.strip()
    if key.startswith("#") or key.isdigit():
        pr = client.get(f"/repos/{repo}/pulls/{key.lstrip('#')}")
        if not pr.get("merged_at"):
            raise LookupError(f"pull request #{key.lstrip('#')} is not merged")
        return str(pr["merge_commit_sha"])
    return key


def read(client: Client, repo: str, key: str, branch: str = DEFAULT_BRANCH) -> dict[str, Any]:
    merge_sha = resolve(client, repo, key)
    try:
        data = client.get(f"/repos/{repo}/contents/{path_for(merge_sha)}", ref=branch)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise LookupError(f"no receipt for {merge_sha[:7]} on {branch}") from exc
        raise
    text = base64.b64decode(data["content"]).decode("utf-8")
    return dict(json.loads(text))


def summary(doc: dict[str, Any]) -> str:
    """A few lines a person can read: who merged what, what it proved."""
    meta = doc["receipt"]
    report = Report.model_validate(doc["report"])
    lines = [
        f"#{meta['pull_request']} merged as {str(meta['merge_commit_sha'])[:7]} by {meta['merged_by'] or '?'}"
        f" at {meta['merged_at'] or '?'}",
        f"head {str(meta['head_sha'])[:7]} · policy {meta['policy']} ({str(meta['policy_sha256'])[:12]})"
        f" · mergeproof {meta['mergeproof']}",
        f"verdict: {meta['verdict']} · {meta['headline']}",
        "",
    ]
    for rule, req in report.requirements:
        lines.append(f"[{req.effective.value:>7}] {rule.id} · {req.label}: {req.outcome.summary}")
        lines += [f"          {d}" for d in req.outcome.details[:3]]
    return "\n".join(lines)
