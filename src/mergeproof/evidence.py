"""The evidence block: a fenced YAML mapping inside a PR description.

Machines read it, agents write it, humans can still skim it::

    ```evidence
    environment: staging
    links:
      - before: https://logs.example.com/run/1
        after: https://logs.example.com/run/2
    ```
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

FENCE = re.compile(r"^```[ \t]*(?P<tag>[\w.-]+)[^\n]*\n(?P<body>.*?)^```[ \t]*$", re.S | re.M)


@dataclass
class Evidence:
    data: dict[str, Any] = field(default_factory=dict)
    found: bool = False
    errors: list[str] = field(default_factory=list)

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                return default
        return node

    def has(self, path: str) -> bool:
        missing = object()
        return self.get(path, missing) is not missing


def parse(text: str | None, tag: str = "evidence") -> Evidence:
    """Collect every ```<tag> block in *text*; later blocks override earlier keys."""
    result = Evidence()
    if not text:
        return result
    for m in FENCE.finditer(text.replace("\r\n", "\n")):
        if m.group("tag") != tag:
            continue
        result.found = True
        try:
            loaded = yaml.safe_load(m.group("body"))
        except yaml.YAMLError as exc:
            result.errors.append(f"{tag} block is not valid YAML: {exc}")
            continue
        if loaded is None:
            continue
        if not isinstance(loaded, dict):
            result.errors.append(f"{tag} block must be a mapping, got {type(loaded).__name__}")
            continue
        result.data.update(loaded)
    return result


def render(data: dict[str, Any], tag: str = "evidence") -> str:
    """Format *data* as a fenced block ready to paste into a PR description."""
    if not data:
        return ""
    body = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True).rstrip()
    return f"```{tag}\n{body}\n```"


def merge_templates(templates: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge evidence skeletons; the first value for a key wins."""
    merged: dict[str, Any] = {}
    for tmpl in templates:
        _merge_into(merged, tmpl)
    return merged


def _merge_into(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _merge_into(dst[key], value)
        else:
            dst.setdefault(key, value)
