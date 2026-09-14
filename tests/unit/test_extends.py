import hashlib
import textwrap

import httpx
import pytest
import respx

from mergeproof import extends, policy

BASE = textwrap.dedent(
    """
    version: 1
    project: org
    rules:
      - id: a
        when: { paths: ["src/**"] }
        require: [{ check: files.changed, with: { any_of: ["tests/**"] } }]
      - id: b
        severity: warn
        when: { paths: ["src/**"] }
        require: [{ check: files.changed, with: { any_of: ["CHANGELOG.md"] } }]
    """
)


def write(tmp_path, name, text):
    (tmp_path / name).write_text(textwrap.dedent(text))
    return tmp_path / name


def test_local_file_replaces_disables_and_adds(tmp_path):
    write(tmp_path, "base.yaml", BASE)
    local = write(
        tmp_path,
        "mergeproof.yaml",
        """
        extends: path:base.yaml
        project: svc
        rules:
          - id: a
            when: { paths: ["lib/**"] }
            require: [{ check: files.changed, with: { any_of: ["lib/tests/**"] } }]
          - id: b
            enabled: false
          - id: c
            when: { labels: ["x"] }
            require: [{ check: pr.labels, with: { any_of: ["ok"] } }]
        """,
    )
    pol = policy.load(local)
    assert [r.id for r in pol.rules] == ["a", "c"] and pol.project == "svc" and pol.inherited
    assert pol.rules[0].when.paths == ["lib/**"] and pol.rules[0].source == ""  # replaced locally
    assert pol.rules[1].source == ""


def test_untouched_base_rules_keep_their_source(tmp_path):
    write(tmp_path, "base.yaml", BASE)
    local = write(tmp_path, "mergeproof.yaml", "extends: [path:base.yaml]\nrules: []\n")
    pol = policy.load(local)
    assert [r.id for r in pol.rules] == ["a", "b"]
    assert pol.rules[0].source == "path:base.yaml" and pol.project == "org"


def test_bases_can_extend_bases_relative_to_themselves(tmp_path):
    (tmp_path / "org").mkdir()
    write(tmp_path / "org", "root.yaml", BASE)
    write(tmp_path / "org", "python.yaml", "extends: path:root.yaml\nrules:\n  - id: b\n    enabled: false\n")
    local = write(tmp_path, "mergeproof.yaml", "extends: path:org/python.yaml\nrules: []\n")
    pol = policy.load(local)
    assert [r.id for r in pol.rules] == ["a"] and pol.rules[0].source == "path:root.yaml"


def test_errors_are_specific(tmp_path):
    write(tmp_path, "base.yaml", BASE)
    with pytest.raises(policy.PolicyError, match="disabled but no base defines it"):
        policy.load(write(tmp_path, "p1.yaml", "extends: path:base.yaml\nrules:\n  - id: zz\n    enabled: false\n"))
    with pytest.raises(policy.PolicyError, match="not found"):
        policy.load(write(tmp_path, "p2.yaml", "extends: path:missing.yaml\nrules: []\n"))
    with pytest.raises(policy.PolicyError, match="use `path:"):
        policy.load(write(tmp_path, "p3.yaml", "extends: http://x/y.yaml\nrules: []\n"))
    write(tmp_path, "loop-a.yaml", "extends: path:loop-b.yaml\nrules: []\n")
    write(tmp_path, "loop-b.yaml", "extends: path:loop-a.yaml\nrules: []\n")
    with pytest.raises(policy.PolicyError, match="cycle"):
        policy.load(tmp_path / "loop-a.yaml")
    with pytest.raises(policy.PolicyError, match="pin to a commit sha or a version tag"):
        policy.load(write(tmp_path, "p4.yaml", "extends: github:o/r/base.yaml@main\nrules: []\n"))
    with pytest.raises(policy.PolicyError, match="expected github:OWNER"):
        policy.load(write(tmp_path, "p5.yaml", "extends: github:nonsense\nrules: []\n"))


@respx.mock
def test_github_bases_are_fetched_pinned_verified_and_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGEPROOF_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    sha = "a" * 40
    digest = hashlib.sha256(BASE.encode()).hexdigest()
    by_tag = respx.get("https://raw.githubusercontent.com/acme/policies/v1/python.yaml").mock(
        return_value=httpx.Response(200, text=BASE)
    )
    by_sha = respx.get(f"https://raw.githubusercontent.com/acme/policies/{sha}/python.yaml").mock(
        return_value=httpx.Response(200, text=BASE)
    )
    respx.get("https://raw.githubusercontent.com/acme/policies/v2/python.yaml").mock(
        return_value=httpx.Response(200, text=BASE + "# changed\n")
    )
    respx.get("https://raw.githubusercontent.com/acme/policies/v3/python.yaml").mock(return_value=httpx.Response(404))

    pol = policy.load(write(tmp_path, "tag.yaml", "extends: github:acme/policies/python.yaml@v1\nrules: []\n"))
    assert pol.rules[0].source == "github:acme/policies/python.yaml@v1"
    assert by_tag.calls[0].request.headers["Authorization"] == "Bearer tok"
    policy.load(tmp_path / "tag.yaml")
    assert by_tag.call_count == 2, "tags may move, so they are not cached"

    spec = f"extends: github:acme/policies/python.yaml@{sha}\nrules: []\n"
    policy.load(write(tmp_path, "sha.yaml", spec))
    policy.load(tmp_path / "sha.yaml")
    assert by_sha.call_count == 1, "a sha is immutable, so it is cached"

    pinned = f"extends: github:acme/policies/python.yaml@v1#sha256={digest}\nrules: []\n"
    assert policy.load(write(tmp_path, "digest.yaml", pinned)).rules
    wrong = f"extends: github:acme/policies/python.yaml@v2#sha256={digest}\nrules: []\n"
    with pytest.raises(policy.PolicyError, match="does not match the pinned sha256"):
        policy.load(write(tmp_path, "wrong.yaml", wrong))
    with pytest.raises(policy.PolicyError, match="HTTP 404"):
        policy.load(write(tmp_path, "gone.yaml", "extends: github:acme/policies/python.yaml@v3\nrules: []\n"))


def test_spec_pinning_rules():
    assert (
        extends.VERSION_TAG.match("v1")
        and extends.VERSION_TAG.match("2.3.0")
        and extends.VERSION_TAG.match("v1.2.0-rc.1")
    )
    assert not extends.VERSION_TAG.match("main") and not extends.VERSION_TAG.match("release/1")
