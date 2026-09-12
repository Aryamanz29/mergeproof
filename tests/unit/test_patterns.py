import pytest

from mergeproof import patterns


def test_captures_and_globstar():
    m = patterns.match("src/{pkg}/{name}.py", "src/api/users.py")
    assert m is not None and m.groupdict() == {"pkg": "api", "name": "users"}
    assert patterns.match("tests/**/test_{name}*.py", "tests/unit/api/test_users_extra.py")
    assert patterns.match("**/*.py", "a.py")
    assert patterns.match("**", "deep/er/file")
    assert not patterns.match("src/*.py", "src/sub/a.py")
    assert patterns.match("a?c", "abc") and not patterns.match("a?c", "a/c")


def test_expand_and_errors():
    assert patterns.expand("tests/{pkg}/test_{name}.py", {"pkg": "api", "name": "x"}) == "tests/api/test_x.py"
    with pytest.raises(KeyError):
        patterns.expand("tests/{other}.py", {"name": "x"})
    with pytest.raises(ValueError):
        patterns.compile_glob("src/{unclosed")
    with pytest.raises(ValueError):
        patterns.compile_glob("src/{not-valid}")


def test_select_with_exclusions():
    paths = ["a/b.py", "a/__init__.py", "c.py", "a/deep/d.py"]
    assert patterns.select(paths, ["a/**"], ["**/__init__.py"]) == ["a/b.py", "a/deep/d.py"]
    assert patterns.matches_any(["*.md", "*.py"], "c.py")
