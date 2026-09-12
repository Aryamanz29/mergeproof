from mergeproof import evidence

BODY = """## Summary

```evidence
environment: staging
links:
  - what: login
    before: https://x/1
    after: https://x/2
```

```python
print("not evidence")
```
"""


def test_parse_reads_only_tagged_blocks():
    ev = evidence.parse(BODY)
    assert ev.found and not ev.errors
    assert ev.get("environment") == "staging"
    assert ev.get("links.0.what") == "login"
    assert ev.has("links") and not ev.has("image")
    assert ev.get("links.5.what", "none") == "none"


def test_parse_reports_problems_instead_of_hiding_them():
    assert not evidence.parse("no block").found
    assert not evidence.parse(None).found
    listy = evidence.parse("```evidence\n- a\n- b\n```")
    assert listy.found and listy.errors and listy.data == {}
    broken = evidence.parse("```evidence\nkey: [oops\n```")
    assert "not valid YAML" in broken.errors[0]
    empty = evidence.parse("```evidence\n\n```")
    assert empty.found and not empty.errors


def test_multiple_blocks_merge_and_crlf_is_fine():
    ev = evidence.parse("```evidence\r\na: 1\r\n```\r\n\r\n```evidence\r\nb: 2\r\na: 3\r\n```")
    assert ev.data == {"a": 3, "b": 2}


def test_render_roundtrip_and_merge_templates():
    text = evidence.render({"environment": "staging", "links": [{"before": "<url>"}]})
    assert text.startswith("```evidence\n") and text.endswith("```")
    assert evidence.parse(text).get("links.0.before") == "<url>"
    assert evidence.render({}) == ""
    merged = evidence.merge_templates([{"a": {"x": 1}}, {"a": {"y": 2}, "b": 3}, {"b": 4}])
    assert merged == {"a": {"x": 1, "y": 2}, "b": 3}
