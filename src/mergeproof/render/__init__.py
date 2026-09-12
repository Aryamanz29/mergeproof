"""Turn a :class:`Report` into text for a terminal, Markdown for a PR, or a prompt for an agent."""

from mergeproof.render.agent import agent_prompt
from mergeproof.render.markdown import MARKER, explain_markdown, report_markdown
from mergeproof.render.text import report_text

FORMATS = ("text", "md", "json")

__all__ = ["FORMATS", "MARKER", "agent_prompt", "explain_markdown", "report_markdown", "report_text"]
