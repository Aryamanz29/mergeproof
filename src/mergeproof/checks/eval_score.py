"""An evaluation run scored above the bar: the check behind `braintrust.eval` and `langfuse.eval`.

"Traces exist" is the first question for a model or prompt change; "did the
eval stay above the bar" is the second. This module holds the part that does
not depend on the backend: reading the run reference from the evidence block,
comparing scores with thresholds, and explaining the result. A plugin
subclasses :class:`EvalScore` and implements :meth:`EvalScore.fetch_run`.
"""

from __future__ import annotations

import re
from abc import abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from mergeproof.checks.base import Check, error, fail, ok, pending
from mergeproof.context import Context
from mergeproof.report import Outcome


class EvalRun(BaseModel):
    """What a backend knows about one evaluation run."""

    id: str
    scores: dict[str, float]
    name: str | None = None
    at: str | None = None
    count: int | None = Field(default=None, description="Examples in the run")
    url: str | None = None

    def line(self, source: str) -> str:
        parts = [source, self.name or self.id, f"{self.count} examples" if self.count is not None else None, self.at]
        return " · ".join(p for p in parts if p)


class MissingCredentials(RuntimeError):
    """Raised by a backend when it has no way to authenticate; the requirement stays pending."""


class EvalScore(Check):
    """Abstract. Subclasses set ``id``, ``source`` and ``fetch_run``; the rest is shared."""

    id: ClassVar[str] = "eval.score"
    source: ClassVar[str] = "eval"
    description: ClassVar[str] = "An evaluation run named in the evidence block scores at least the thresholds given."

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

        key: str = Field(default="eval", description="Evidence field holding the run's id, name or URL")
        scorers: dict[str, float] = Field(min_length=1, description="Scorer name -> minimum score")
        pattern: str | None = Field(
            default=None, description="Regex a URL reference must match; named groups reach `fetch_run`"
        )
        baseline_key: str = Field(default="eval_baseline", description="Evidence field holding a run to compare with")
        max_regression: float | None = Field(
            default=None, description="With a baseline run, no scorer may drop by more than this"
        )
        example: str = "<experiment id or URL>"
        block: str = "evidence"

    @abstractmethod
    def fetch_run(self, ref: str, match: re.Match[str] | None, params: Any) -> EvalRun:
        """Resolve *ref* (an id, a name or a URL) to a run with its scores."""

    def run(self, ctx: Context, params: Params, files: list[str]) -> Outcome:
        ev = ctx.evidence(params.block)
        if ev.errors:
            return fail("evidence block could not be parsed", details=ev.errors, fix=self.fix(params))
        ref = ev.get(params.key)
        if not ref:
            return fail(f"no `{params.key}` in the evidence block", fix=self.fix(params))
        try:
            run = self.resolve(str(ref), params)
            baseline = None
            if params.max_regression is not None and ev.get(params.baseline_key):
                baseline = self.resolve(str(ev.get(params.baseline_key)), params)
        except ValueError as exc:
            return fail(str(exc), fix=self.fix(params))
        except MissingCredentials as exc:
            return pending(f"{self.source}: {exc}", fix=self.fix(params))
        except Exception as exc:
            return error(f"{self.source}: {type(exc).__name__}: {exc}")

        details = [run.line(self.source)]
        problems: list[str] = []
        for name, minimum in params.scorers.items():
            score = run.scores.get(name)
            if score is None:
                problems.append(f"{name}: not scored in this run")
                details.append(f"{name}: not scored")
                continue
            mark = "≥" if score >= minimum else "<"
            details.append(f"{name} {score:.2f} {mark} {minimum:.2f}")
            if score < minimum:
                problems.append(f"{name} {score:.2f} is below {minimum:.2f}")
            if baseline is not None and params.max_regression is not None and name in baseline.scores:
                drop = baseline.scores[name] - score
                details[-1] += f" (baseline {baseline.scores[name]:.2f}, {'-' if drop > 0 else '+'}{abs(drop):.2f})"
                if drop > params.max_regression:
                    problems.append(f"{name} dropped {drop:.2f} against the baseline (limit {params.max_regression})")
        data: dict[str, Any] = {"run": run.model_dump(exclude_none=True), "scores": run.scores}
        if baseline is not None:
            data["baseline"] = baseline.model_dump(exclude_none=True)
        if problems:
            return fail("; ".join(problems), details=details, fix=self.fix(params), data=data)
        met = ", ".join(f"{n} {run.scores[n]:.2f}" for n in params.scorers)
        return ok(f"{self.source} run scores {met}", details=details, data=data)

    def resolve(self, ref: str, params: Params) -> EvalRun:
        match = None
        if params.pattern and re.match(r"^https?://", ref):
            match = re.match(params.pattern, ref)
            if match is None:
                raise ValueError(f"`{ref}` does not look like a {self.source} run link")
        return self.fetch_run(ref, match, params)

    def fix(self, params: Params) -> str:
        bar = ", ".join(f"{n} ≥ {m}" for n, m in params.scorers.items())
        return (
            f"Run the evaluation for this change on {self.source} and put the run's id or link under "
            f"`{params.key}` in the evidence block; it must score {bar}."
        )

    def explain(self, params: Params) -> str:
        bar = ", ".join(f"`{n}` ≥ {m}" for n, m in params.scorers.items())
        text = f"An evaluation run named under `{params.key}` in the evidence block scores {bar} on {self.source}"
        if params.max_regression is not None:
            text += f"; with `{params.baseline_key}`, no scorer drops by more than {params.max_regression}"
        return text + "."

    def evidence_template(self, params: Params) -> dict[str, Any]:
        template: dict[str, Any] = {params.key: params.example}
        if params.max_regression is not None:
            template[params.baseline_key] = params.example
        return template
