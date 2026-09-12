from mergeproof.evidence import parse_evidence, render_template

BODY = """## Summary
stuff

```evidence
tenant: ai-eval
traces:
  - tool: query_assets
    before: https://x/?r=a
    after: https://x/?r=b
```

```python
print("not evidence")
```
"""


def test_parse_block():
    ev = parse_evidence(BODY)
    assert ev.found and not ev.errors
    assert ev.get("tenant") == "ai-eval"
    assert ev.get("traces.0.tool") == "query_assets"
    assert ev.has("traces") and not ev.has("image")


def test_missing_and_invalid():
    assert not parse_evidence("no block here").found
    bad = parse_evidence("```evidence\n- just\n- a list\n```")
    assert bad.found and bad.errors and bad.data == {}
    broken = parse_evidence("```evidence\nkey: [unclosed\n```")
    assert broken.errors


def test_merge_multiple_blocks_and_crlf():
    body = "```evidence\r\na: 1\r\n```\r\n\r\n```evidence\r\nb: 2\r\n```"
    ev = parse_evidence(body)
    assert ev.data == {"a": 1, "b": 2}


def test_render_template_roundtrip():
    md = render_template({"tenant": "ai-eval", "traces": [{"before": "<url>"}]})
    assert md.startswith("```evidence\n") and "tenant: ai-eval" in md
    assert parse_evidence(md).get("traces.0.before") == "<url>"
