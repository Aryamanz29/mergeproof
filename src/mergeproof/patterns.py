"""Path globs with ``**``, ``*``, ``?`` and named ``{capture}`` segments.

``src/{pkg}/{name}.py`` matched against ``src/api/users.py`` yields
``pkg=api`` and ``name=users``; :func:`expand` substitutes those into a
second glob such as ``tests/{pkg}/test_{name}*.py``.
"""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=4096)
def compile_glob(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif ch == "*":
            parts.append("[^/]*")
            i += 1
        elif ch == "?":
            parts.append("[^/]")
            i += 1
        elif ch == "{":
            end = pattern.find("}", i)
            if end < 0:
                raise ValueError(f"unclosed '{{' in {pattern!r}")
            name = pattern[i + 1 : end]
            if not name.isidentifier():
                raise ValueError(f"bad capture name {name!r} in {pattern!r}")
            parts.append(f"(?P<{name}>[^/]+)")
            i = end + 1
        else:
            parts.append(re.escape(ch))
            i += 1
    return re.compile("^" + "".join(parts) + "$")


def match(pattern: str, path: str) -> re.Match[str] | None:
    return compile_glob(pattern).match(path)


def matches_any(patterns: list[str], path: str) -> bool:
    return any(match(p, path) for p in patterns)


def expand(template: str, captures: dict[str, str]) -> str:
    def replace(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in captures:
            raise KeyError(f"{template!r} uses {{{key}}} which the source glob did not capture")
        return captures[key]

    return re.sub(r"\{(\w+)\}", replace, template)


def select(paths: list[str], include: list[str], exclude: list[str] | None = None) -> list[str]:
    excluded = exclude or []
    return [p for p in paths if matches_any(include, p) and not matches_any(excluded, p)]
