"""The JSON schema for mergeproof.yaml, derived from the same models that validate it.

Published with the docs at SCHEMA_URL so editors can complete and lint the
file. `mergeproof schema` prints it; a test keeps the committed copy in sync.
"""

from __future__ import annotations

import json
from typing import Any

from mergeproof.policy import Policy

SCHEMA_VERSION = 1
SCHEMA_URL = f"https://aryamanz29.github.io/mergeproof/schema/mergeproof-v{SCHEMA_VERSION}.json"
EDITOR_HINT = f"# yaml-language-server: $schema={SCHEMA_URL}"


def json_schema() -> dict[str, Any]:
    """What a policy file may contain, as JSON Schema draft 2020-12."""
    schema = Policy.model_json_schema()
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_URL,
        "title": "mergeproof policy",
        "description": "Rules of the form: when a change touches X, it must prove Y.",
        **schema,
    }
    props = schema["properties"]
    props["version"] = {"type": "integer", "const": SCHEMA_VERSION, "default": SCHEMA_VERSION}
    props["extends"] = {
        "description": "Base policies to inherit, applied in order before this file: "
        "`github:OWNER/REPO/file.yaml@REF` (a tag or sha) or `path:relative/file.yaml`.",
        "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
    }
    rule = schema["$defs"]["Rule"]["properties"]
    rule.pop("source", None)
    rule["enabled"] = {
        "type": "boolean",
        "default": True,
        "description": "Set to false to switch off a rule inherited through `extends`.",
    }
    schema["$defs"]["Rule"]["required"] = ["id"]  # `require` may be absent when a rule only disables a base one
    schema["$defs"]["Requirement"]["properties"]["with"]["description"] = (
        "Parameters for the check; `mergeproof checks` lists them and validate checks them."
    )
    return schema


def dumps() -> str:
    return json.dumps(json_schema(), indent=2, sort_keys=False) + "\n"
