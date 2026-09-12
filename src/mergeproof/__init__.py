"""mergeproof: evidence gates for pull requests.

A *policy* (``mergeproof.yaml``) declares rules of the form
"when a change touches X, it must come with evidence Y".
The same policy drives three things:

* ``mergeproof check``        - CI gate that posts a report on the PR
* ``mergeproof explain``      - agent/human-facing: what must this diff prove, and what is missing now
* ``mergeproof agent-prompt`` - a Markdown block for CLAUDE.md / AGENTS.md generated from the policy
"""

from .checks.base import Check
from .models import CheckResult, Policy, Report, Requirement, Rule, Severity, Status

__version__ = "0.1.0"
__all__ = [
    "Check",
    "CheckResult",
    "Policy",
    "Report",
    "Requirement",
    "Rule",
    "Severity",
    "Status",
    "__version__",
]
