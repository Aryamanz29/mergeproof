"""Evidence gates for pull requests.

A policy file declares what a change must prove before it merges. The same
policy is enforced in CI and explained to contributors and coding agents.

Everything imported here is the public API for plugins and policies. It
follows semantic versioning: from 1.0 it changes incompatibly only in a
major release, after a deprecation period announced in the changelog.
Anything else under ``mergeproof.*`` is internal and may change in a minor.
"""

from mergeproof.checks.base import Check, error, fail, ok, pending, skip, warn
from mergeproof.checks.eval_score import EvalRun, EvalScore, MissingCredentials
from mergeproof.context import ChangedFile, CheckRun, Comment, Context
from mergeproof.policy import Policy, PolicyError, Requirement, Rule, Severity, When
from mergeproof.report import Annotation, Outcome, Report, RequirementResult, RuleResult, Status
from mergeproof.verifiers.base import Verification, Verifier

__version__ = "1.0.0"  # x-release-please-version

__all__ = [
    "Annotation",
    "ChangedFile",
    "Check",
    "CheckRun",
    "Comment",
    "Context",
    "EvalRun",
    "EvalScore",
    "MissingCredentials",
    "Outcome",
    "Policy",
    "PolicyError",
    "Report",
    "Requirement",
    "RequirementResult",
    "Rule",
    "RuleResult",
    "Severity",
    "Status",
    "Verification",
    "Verifier",
    "When",
    "__version__",
    "error",
    "fail",
    "ok",
    "pending",
    "skip",
    "warn",
]
