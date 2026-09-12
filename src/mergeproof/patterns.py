"""Glob matching with `**`, `*`, `?` and named `{capture}` segments."""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=1024)
def glob_to_regex(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "{":
            j = pattern.find("}", i)
            if j == -1:
                raise ValueError(f"unclosed '{{' in pattern {pattern!r}")
            name = pattern[i + 1 : j]
            if not name.isidentifier():
                raise ValueError(f"bad capture name {name!r} in pattern {pattern!r}")
            out.append(f"(?P<{name}>[^/]+)")
            i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def match(pattern: str, path: str) -> re.Match[str] | None:
    return glob_to_regex(pattern).match(path)


def any_match(patterns: list[str], path: str) -> bool:
    return any(match(p, path) for p in patterns)


def expand(template: str, groups: dict[str, str]) -> str:
    """Substitute `{name}` captures into a glob template."""

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in groups:
            raise KeyError(f"template {template!r} references unknown capture {key!r}")
        return groups[key]

    return re.sub(r"\{(\w+)\}", sub, template)


def filter_paths(paths: list[str], include: list[str], exclude: list[str] | None = None) -> list[str]:
    exclude = exclude or []
    return [p for p in paths if any_match(include, p) and not any_match(exclude, p)]
