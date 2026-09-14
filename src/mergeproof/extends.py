"""Policy inheritance: `extends` pulls rules from other policy files.

An organisation with twenty repositories should not paste the same rules
twenty times. A policy may extend one or more bases; the local file then
adds rules, replaces a base rule by ``id``, or switches one off with
``enabled: false``. Bases are pinned, never floating: a pull request must
not be able to change its own gate by pushing to a branch somewhere else.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

import httpx
import yaml

GITHUB_SPEC = re.compile(
    r"^github:(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?P<path>[^@#]+)@(?P<ref>[^#]+)(?:#sha256=(?P<digest>[0-9a-f]{64}))?$"
)
SHA = re.compile(r"^[0-9a-f]{40}$")
VERSION_TAG = re.compile(r"^v?\d+(\.\d+)*([-+.][\w.]+)?$")
MAX_DEPTH = 5
TOP_LEVEL = ("version", "project", "evidence_block")


class ExtendsError(ValueError):
    pass


def resolve(raw: dict[str, Any], origin: str | Path, *, _chain: tuple[str, ...] = ()) -> dict[str, Any]:
    """Fold every base named by ``extends`` into *raw* and return one flat policy document.

    Rules carry a ``source`` saying which file defined them. *origin* is where *raw* came from;
    ``path:`` bases are resolved relative to it.
    """
    if not isinstance(raw, dict):
        return raw
    label = str(origin)
    specs = raw.pop("extends", None)
    bases = [specs] if isinstance(specs, str) else list(specs or [])
    if len(_chain) >= MAX_DEPTH:
        raise ExtendsError(f"{label}: extends nested more than {MAX_DEPTH} levels deep")
    merged: dict[str, Any] = {"rules": [], "extends": []}
    for spec in bases:
        if not isinstance(spec, str):
            raise ExtendsError(f"{label}: extends entries must be strings")
        text, base_origin = fetch(spec, origin)
        if base_origin in _chain or base_origin == label:
            raise ExtendsError(f"{label}: extends cycle through {spec}")
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ExtendsError(f"{spec}: not valid YAML: {exc}") from None
        if not isinstance(doc, dict):
            raise ExtendsError(f"{spec}: not a policy document")
        doc = resolve(doc, base_origin, _chain=(*_chain, label))
        for rule in doc.get("rules") or []:
            if isinstance(rule, dict) and rule.get("source") == base_origin:
                rule["source"] = spec  # name the base the way the policy does, not by absolute path
        merge_into(merged, doc, spec)
        merged["extends"] = [*merged["extends"], *doc.get("extends", []), spec]
    merge_into(merged, raw, label)
    return merged


def merge_into(merged: dict[str, Any], doc: dict[str, Any], label: str) -> None:
    for key in TOP_LEVEL:
        if key in doc:
            merged[key] = doc[key]
    for key in doc:
        if key not in (*TOP_LEVEL, "rules", "extends"):
            merged[key] = doc[key]  # let the schema complain about it with the right name
    rules: list[dict[str, Any]] = merged["rules"]
    by_id = {r.get("id"): i for i, r in enumerate(rules)}
    for rule in doc.get("rules") or []:
        if not isinstance(rule, dict) or not rule.get("id"):
            rules.append(rule)  # schema error, reported downstream
            continue
        rule = dict(rule)
        enabled = rule.pop("enabled", True)
        rid = rule["id"]
        if enabled is False:
            if rid not in by_id:
                raise ExtendsError(f"{label}: rule {rid!r} is disabled but no base defines it")
            rules.pop(by_id[rid])
            by_id = {r.get("id"): i for i, r in enumerate(rules)}
            continue
        rule.setdefault("source", label)
        if rid in by_id:
            rules[by_id[rid]] = rule
        else:
            by_id[rid] = len(rules)
            rules.append(rule)


def fetch(spec: str, origin: str | Path) -> tuple[str, str]:
    """The text of a base and the origin to resolve its own `path:` entries against."""
    if spec.startswith("path:"):
        base = Path(origin).parent if Path(origin).suffix else Path(origin)
        target = (base / spec[len("path:") :]).resolve()
        try:
            return target.read_text(encoding="utf-8"), str(target)
        except FileNotFoundError:
            raise ExtendsError(f"extends {spec}: {target} not found") from None
    if spec.startswith("github:"):
        return fetch_github(spec), spec
    raise ExtendsError(f"extends {spec!r}: use `path:relative/file.yaml` or `github:OWNER/REPO/file.yaml@REF`")


def fetch_github(spec: str) -> str:
    m = GITHUB_SPEC.match(spec)
    if not m:
        raise ExtendsError(f"extends {spec!r}: expected github:OWNER/REPO/path.yaml@REF[#sha256=...]")
    owner, repo, path, ref, digest = m.group("owner", "repo", "path", "ref", "digest")
    pinned = bool(SHA.match(ref) or digest or VERSION_TAG.match(ref))
    if not pinned:
        raise ExtendsError(f"extends {spec!r}: pin to a commit sha or a version tag, not a branch")
    cache = cache_path(spec) if (SHA.match(ref) or digest) else None
    if cache and cache.exists():
        return cache.read_text(encoding="utf-8")
    headers = {"User-Agent": "mergeproof"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path.lstrip('/')}"
    try:
        response = httpx.get(url, headers=headers, timeout=20.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise ExtendsError(f"extends {spec!r}: {type(exc).__name__} fetching {url}") from None
    if response.status_code != 200:
        raise ExtendsError(f"extends {spec!r}: HTTP {response.status_code} fetching {url}")
    text = response.text
    if digest and hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
        raise ExtendsError(f"extends {spec!r}: content does not match the pinned sha256")
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
    return text


def cache_path(spec: str) -> Path:
    root = os.environ.get("MERGEPROOF_CACHE_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "mergeproof")
    return Path(root) / "extends" / (hashlib.sha256(spec.encode("utf-8")).hexdigest() + ".yaml")
