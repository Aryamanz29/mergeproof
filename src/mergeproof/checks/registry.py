from __future__ import annotations

from importlib.metadata import entry_points

from .base import Check


class UnknownCheck(KeyError):
    pass


class Registry:
    def __init__(self) -> None:
        self._checks: dict[str, type[Check]] = {}

    def register(self, check_cls: type[Check]) -> type[Check]:
        self._checks[check_cls.id] = check_cls
        return check_cls

    def get(self, check_id: str) -> Check:
        try:
            return self._checks[check_id]()
        except KeyError:
            known = ", ".join(sorted(self._checks))
            raise UnknownCheck(f"unknown check {check_id!r}; registered: {known}") from None

    def ids(self) -> list[str]:
        return sorted(self._checks)

    def classes(self) -> dict[str, type[Check]]:
        return dict(self._checks)


def builtin_registry() -> Registry:
    from . import agent_verdict, body, ci_job, evidence_field, human_verified, labels, shell, tests_changed, traces

    reg = Registry()
    for cls in (
        tests_changed.TestsChanged,
        evidence_field.EvidenceField,
        traces.EvidenceTraces,
        ci_job.CiJobPassed,
        human_verified.HumanVerified,
        labels.Labels,
        body.Body,
        shell.Shell,
        agent_verdict.AgentVerdict,
    ):
        reg.register(cls)
    return reg


def default_registry(load_plugins: bool = True) -> Registry:
    reg = builtin_registry()
    if load_plugins:
        for ep in entry_points(group="mergeproof.checks"):
            if ep.value.startswith("mergeproof.checks."):
                continue  # builtins already loaded
            reg.register(ep.load())
    return reg
