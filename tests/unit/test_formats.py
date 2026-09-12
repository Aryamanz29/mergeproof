import json
import textwrap
from xml.etree import ElementTree as ET

from mergeproof import engine, policy, render
from mergeproof.checks.registry import builtin_registry

from .conftest import make_context

POLICY = textwrap.dedent("""
    rules:
      - id: tests
        when: { paths: ["src/**"] }
        require:
          - check: tests.changed
            with: { map: { "src/{name}.py": "tests/test_{name}.py" } }
          - check: ci.job_passed
            with: { name: unit }
      - id: labels
        severity: warn
        require:
          - check: pr.labels
            with: { any_of: [ok] }
""")


def report():
    pol = policy.loads(POLICY)
    return engine.evaluate(pol, make_context(files=["src/a.py", "src/b.py"], labels=["ok"]), builtin_registry())


def test_junit_maps_rules_to_suites_and_requirements_to_cases():
    doc = ET.fromstring(render.junit_xml(report()))
    assert doc.tag == "testsuites" and doc.get("tests") == "3"
    assert doc.get("failures") == "1" and doc.get("skipped") == "1"
    suites = {s.get("name"): s for s in doc.findall("testsuite")}
    assert set(suites) == {"tests", "labels"}
    cases = {c.get("name"): c for c in suites["tests"].findall("testcase")}
    failure = cases["tests.changed"].find("failure")
    assert failure is not None and "without test changes" in failure.get("message")
    assert "src/a.py" in failure.text and "fix:" in failure.text
    assert cases["ci.job_passed"].find("skipped").get("message").startswith("pending:")
    assert suites["labels"].find("testcase").find("failure") is None


def test_rdjson_carries_file_annotations():
    data = json.loads(render.rdjson(report()))
    assert data["source"]["name"] == "mergeproof" and data["severity"] == "ERROR"
    paths = sorted(d["location"]["path"] for d in data["diagnostics"])
    assert paths == ["src/a.py", "src/b.py"]
    first = data["diagnostics"][0]
    assert first["severity"] == "ERROR" and first["code"]["value"] == "tests"
    assert first["location"]["range"]["start"]["line"] == 1
    assert first["message"].startswith("tests.changed: expected a changed test matching")
