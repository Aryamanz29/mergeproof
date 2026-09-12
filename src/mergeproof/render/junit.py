"""JUnit XML: one suite per rule, one case per requirement.

Test-result renderers such as EnricoMi/publish-unit-test-result-action and dorny/test-reporter
read this and draw the check run, so mergeproof does not have to.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from mergeproof.report import Report, RequirementResult, Status


def junit_xml(report: Report) -> str:
    suites = ET.Element("testsuites", name="mergeproof")
    total = failures = skipped = 0
    for rule in report.matched:
        suite = ET.SubElement(suites, "testsuite", name=rule.id, timestamp=report.evaluated_at)
        for req in rule.requirements:
            total += 1
            case = ET.SubElement(suite, "testcase", name=req.label, classname=rule.id)
            status = req.outcome.status
            if status in (Status.FAIL, Status.ERROR) or (status == Status.WARN):
                failures += 1
                tag = "error" if status == Status.ERROR else "failure"
                node = ET.SubElement(case, tag, message=req.outcome.summary, type=status.value)
                node.text = _body(req)
            elif status in (Status.PENDING, Status.SKIP):
                skipped += 1
                ET.SubElement(case, "skipped", message=f"{status.value}: {req.outcome.summary}")
            out = ET.SubElement(case, "system-out")
            out.text = _body(req)
        suite.set("tests", str(len(rule.requirements)))
        suite.set("failures", str(sum(1 for r in rule.requirements if r.outcome.status in (Status.FAIL, Status.WARN))))
        suite.set("errors", str(sum(1 for r in rule.requirements if r.outcome.status == Status.ERROR)))
        suite.set(
            "skipped", str(sum(1 for r in rule.requirements if r.outcome.status in (Status.PENDING, Status.SKIP)))
        )
    suites.set("tests", str(total))
    suites.set("failures", str(failures))
    suites.set("skipped", str(skipped))
    ET.indent(suites)
    return ET.tostring(suites, encoding="unicode", xml_declaration=True)


def _body(req: RequirementResult) -> str:
    lines = [req.outcome.summary, *req.outcome.details]
    if req.outcome.fix:
        lines.append(f"fix: {req.outcome.fix}")
    if req.instructions:
        lines.append(req.instructions.strip())
    return "\n".join(lines)
