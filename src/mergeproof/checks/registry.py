from __future__ import annotations

import sys
from importlib.metadata import entry_points

from mergeproof.checks.base import Check

ENTRY_POINT_GROUP = "mergeproof.checks"


class Registry:
    def __init__(self) -> None:
        self._checks: dict[str, type[Check]] = {}

    def add(self, check: type[Check]) -> type[Check]:
        self._checks[check.id] = check
        return check

    def lookup(self, check_id: str) -> Check | None:
        cls = self._checks.get(check_id)
        return cls() if cls else None

    def ids(self) -> list[str]:
        return sorted(self._checks)

    def items(self) -> list[tuple[str, type[Check]]]:
        return sorted(self._checks.items())


def builtin_registry() -> Registry:
    from mergeproof.checks import (
        agent_verdict,
        body,
        ci_job,
        evidence_artifacts,
        evidence_field,
        evidence_links,
        files,
        human_verified,
        labels,
        shell,
        tests_changed,
    )

    registry = Registry()
    for check in (
        tests_changed.TestsChanged,
        files.FilesChanged,
        evidence_field.EvidenceField,
        evidence_links.EvidenceLinks,
        evidence_artifacts.EvidenceArtifacts,
        ci_job.CiJobPassed,
        human_verified.HumanVerified,
        agent_verdict.AgentVerdict,
        labels.Labels,
        body.Body,
        shell.Shell,
    ):
        registry.add(check)
    return registry


def load_registry(plugins: bool = True) -> Registry:
    registry = builtin_registry()
    if plugins:
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            if ep.value.startswith("mergeproof.checks."):
                continue
            try:
                registry.add(ep.load())
            except Exception as exc:  # a broken plugin must not take the CLI down
                print(f"mergeproof: plugin check {ep.name!r} could not be loaded: {exc}", file=sys.stderr)
    return registry
