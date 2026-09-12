"""Everything a check may know about a pull request.

A :class:`Context` is plain data. Providers build it from git or the GitHub
API; ``mergeproof context`` prints it as JSON so it can be piped, stored, or
replayed in tests.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from mergeproof import evidence


class ChangedFile(BaseModel):
    path: str
    status: str = "modified"
    previous_path: str | None = None


class Comment(BaseModel):
    author: str
    body: str
    created_at: str = ""
    kind: str = "comment"
    state: str | None = None
    url: str | None = None

    @property
    def is_bot(self) -> bool:
        return self.author.endswith("[bot]")


class CheckRun(BaseModel):
    name: str
    status: str
    conclusion: str | None = None
    url: str | None = None


class Context(BaseModel):
    source: str = "local"
    online: bool = False
    repo: str | None = None
    number: int | None = None
    title: str = ""
    body: str = ""
    author: str = ""
    labels: list[str] = Field(default_factory=list)
    base_ref: str = "main"
    head_sha: str | None = None
    base_sha: str | None = None
    root: str = "."
    files: list[ChangedFile] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    check_runs: list[CheckRun] = Field(default_factory=list)

    @property
    def changed_paths(self) -> list[str]:
        return [f.path for f in self.files if f.status != "removed"]

    @property
    def head_short(self) -> str:
        return (self.head_sha or "")[:7]

    def evidence(self, tag: str = "evidence") -> evidence.Evidence:
        return evidence.parse(self.body, tag)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> Context:
        return cls.model_validate_json(text)


class ContextError(RuntimeError):
    """A context could not be built: bad git ref, missing token, unknown PR."""
