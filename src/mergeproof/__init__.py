"""Evidence gates for pull requests.

A policy file declares what a change must prove before it merges. The same
policy is enforced in CI and explained to contributors and coding agents.
"""

from mergeproof.checks.base import Check
from mergeproof.context import ChangedFile, CheckRun, Comment, Context
from mergeproof.policy import Policy, PolicyError, Requirement, Rule, Severity
from mergeproof.report import Outcome, Report, Status
from mergeproof.verifiers.base import Verifier

__version__ = "0.6.0"  # x-release-please-version

__all__ = [
    "ChangedFile",
    "Check",
    "CheckRun",
    "Comment",
    "Context",
    "Outcome",
    "Policy",
    "PolicyError",
    "Report",
    "Requirement",
    "Rule",
    "Severity",
    "Status",
    "Verifier",
    "__version__",
]
