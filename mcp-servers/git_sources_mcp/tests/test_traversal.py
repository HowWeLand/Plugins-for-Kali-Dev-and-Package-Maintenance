"""The enforcement layer: nothing outside the allowlist or the workdir."""
import pytest

from git_sources_mcp import gitops
from git_sources_mcp.gitops import GitOpsError, resolve_repo, safe_ref, safe_repo_path


def test_unlisted_package_rejected_with_pointer(cfg):
    with pytest.raises(GitOpsError, match="allowlist"):
        resolve_repo(cfg, "not-listed", "upstream")


def test_unknown_remote_rejected(cfg):
    with pytest.raises(GitOpsError, match="remote"):
        resolve_repo(cfg, "demo", "mirror")


def test_missing_remote_kind_rejected(cfg):
    # demo has upstream only.
    with pytest.raises(GitOpsError, match="no salsa remote"):
        resolve_repo(cfg, "demo", "salsa")


def test_clone_path_contained_in_workdir(cfg):
    repo = resolve_repo(cfg, "demo", "upstream")
    assert repo.path.is_relative_to(cfg.workdir.resolve())


def test_option_like_refs_rejected():
    for bad in ("-", "--all", "-x"):
        with pytest.raises(GitOpsError, match="'-'"):
            safe_ref(bad)
    assert safe_ref("HEAD~1") == "HEAD~1"


def test_escaping_paths_rejected():
    for bad in ("/etc/passwd", "../outside", "a/../../b", "--flag"):
        with pytest.raises(GitOpsError, match="Invalid path"):
            safe_repo_path(bad)
    assert safe_repo_path("debian/control") == "debian/control"


def test_grep_pattern_is_not_an_option(cfg):
    """A pattern starting with '-' must reach git as a pattern (after -e),
    not be parsed as an option."""
    gitops.sync(cfg, "demo", "upstream")
    matches, _ = gitops.grep(cfg, "demo", "upstream", "--version", "HEAD", None, 50, 0)
    assert matches == []  # no match — but no error and no option injection
