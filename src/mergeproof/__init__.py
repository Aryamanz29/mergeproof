"""Evidence gates for pull requests.

A policy file declares what a change must prove before it merges. The same
policy is enforced in CI, explained to contributors and coding agents, and
served over MCP.
"""

from mergeproof.checks.base import Check
from mergeproof.context import ChangedFile, CheckRun, Comment, Context
from mergeproof.policy import Policy, PolicyError, Requirement, Rule, Severity
from mergeproof.report import Outcome, Report, Status
from mergeproof.verifiers.base import Verifier

__version__ = "0.2.0"

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
