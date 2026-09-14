import json
from pathlib import Path

from mergeproof import schema

ROOT = Path(__file__).resolve().parents[2]


def test_schema_describes_the_policy_shape():
    s = schema.json_schema()
    assert s["$id"] == schema.SCHEMA_URL and s["$schema"].endswith("2020-12/schema")
    assert s["properties"]["version"]["const"] == 1
    assert {"type": "string"} in s["properties"]["extends"]["oneOf"]
    rule = s["$defs"]["Rule"]["properties"]
    assert "enabled" in rule and "source" not in rule and s["$defs"]["Rule"]["required"] == ["id"]
    assert "with" in s["$defs"]["Requirement"]["properties"]
    assert s["additionalProperties"] is False


def test_committed_schema_is_current():
    committed = json.loads((ROOT / "docs" / "schema" / "mergeproof-v1.json").read_text())
    assert committed == schema.json_schema(), "run `make schema` and commit docs/schema/mergeproof-v1.json"
    assert schema.dumps().endswith("}\n")


def test_editor_hint_points_at_the_published_schema():
    assert f"# yaml-language-server: $schema={schema.SCHEMA_URL}" == schema.EDITOR_HINT
