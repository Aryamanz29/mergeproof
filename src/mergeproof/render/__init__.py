"""Turn a :class:`Report` into text for a terminal, Markdown for a PR, or a prompt for an agent."""

from mergeproof.render.actions import workflow_commands
from mergeproof.render.agent import agent_prompt
from mergeproof.render.junit import junit_xml
from mergeproof.render.markdown import MARKER, explain_markdown, report_markdown
from mergeproof.render.rdjson import rdjson
from mergeproof.render.text import report_text

FORMATS = ("text", "md", "json", "junit", "rdjson")

__all__ = [
    "FORMATS",
    "MARKER",
    "agent_prompt",
    "explain_markdown",
    "junit_xml",
    "rdjson",
    "report_markdown",
    "report_text",
    "workflow_commands",
]
