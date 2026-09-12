"""Parse the structured evidence block out of a PR description.

Contributors (or their coding agents) attach evidence as a fenced YAML block::

    ```evidence
    tenant: staging
    traces:
      - tool: query_assets
        before: https://www.braintrust.dev/app/org/p/proj/logs?r=aaaa
        after:  https://www.braintrust.dev/app/org/p/proj/logs?r=bbbb
    ```

Multiple blocks are shallow-merged in order. Anything that is not valid YAML is an error,
not silently ignored, so the report can say exactly what went wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

_FENCE = re.compile(r"^```[ \t]*(?P<lang>[\w.-]+)[^\n]*\n(?P<body>.*?)^```[ \t]*$", re.S | re.M)


@dataclass
class Evidence:
    data: dict[str, Any] = field(default_factory=dict)
    found: bool = False
    errors: list[str] = field(default_factory=list)

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.data
        for part in dotted.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
                cur = cur[int(part)]
            else:
                return default
        return cur

    def has(self, dotted: str) -> bool:
        sentinel = object()
        return self.get(dotted, sentinel) is not sentinel


def parse_evidence(body: str | None, tag: str = "evidence") -> Evidence:
    ev = Evidence()
    if not body:
        return ev
    body = body.replace("\r\n", "\n")
    for m in _FENCE.finditer(body):
        if m.group("lang") != tag:
            continue
        ev.found = True
        raw = m.group("body")
        try:
            loaded = yaml.safe_load(raw)
        except yaml.YAMLError as exc:  # pragma: no cover - message text varies by version
            ev.errors.append(f"evidence block is not valid YAML: {exc}")
            continue
        if loaded is None:
            continue
        if not isinstance(loaded, dict):
            ev.errors.append(f"evidence block must be a YAML mapping (key: value), got a {type(loaded).__name__}")
            continue
        ev.data.update(loaded)
    return ev


def render_template(template: dict[str, Any], tag: str = "evidence") -> str:
    """Render an evidence skeleton as a fenced block ready to paste into a PR body."""
    if not template:
        return ""
    dumped = yaml.safe_dump(template, sort_keys=False, default_flow_style=False).rstrip()
    return f"```{tag}\n{dumped}\n```"
