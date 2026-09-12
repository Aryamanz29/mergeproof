from mergeproof import patterns


def test_double_star_and_capture():
    m = patterns.match("src/tools/{name}.py", "src/tools/lineage.py")
    assert m and m.group("name") == "lineage"
    assert patterns.match("tests/**/test_{name}*.py", "tests/unit/tools/test_lineage_batch.py")
    assert patterns.match("**/*.py", "a.py")
    assert not patterns.match("src/*.py", "src/sub/a.py")


def test_expand():
    assert patterns.expand("tests/**/test_{name}*.py", {"name": "x"}) == "tests/**/test_x*.py"


def test_filter_paths_exclude():
    out = patterns.filter_paths(["a/b.py", "a/__init__.py", "c.py"], ["a/**"], ["**/__init__.py"])
    assert out == ["a/b.py"]
