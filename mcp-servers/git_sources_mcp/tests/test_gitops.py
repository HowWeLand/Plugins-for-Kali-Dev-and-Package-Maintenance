"""gitops against a local fixture repo — fully offline."""
import pytest

from git_sources_mcp import gitops
from git_sources_mcp.gitops import GitOpsError


def test_sync_clones_then_fetches(cfg):
    r1 = gitops.sync(cfg, "demo", "upstream")
    assert r1.action == "cloned"
    assert r1.tip_before is None
    assert len(r1.tip_after) == 40
    r2 = gitops.sync(cfg, "demo", "upstream")
    assert r2.action == "fetched"
    assert r2.tip_before == r1.tip_after == r2.tip_after
    assert r2.submodule_urls == []


def test_query_before_sync_is_actionable(cfg):
    with pytest.raises(GitOpsError, match="gitsrc_sync"):
        gitops.log(cfg, "demo", "upstream", "HEAD", None, None, 20, 0)


def test_log_pagination_and_filters(cfg):
    gitops.sync(cfg, "demo", "upstream")
    entries, has_more = gitops.log(cfg, "demo", "upstream", "HEAD", None, None, 20, 0)
    assert len(entries) == 2 and not has_more
    assert entries[0]["subject"] == "drop SysV init script for systemd"
    page1, more1 = gitops.log(cfg, "demo", "upstream", "HEAD", None, None, 1, 0)
    assert len(page1) == 1 and more1
    page2, more2 = gitops.log(cfg, "demo", "upstream", "HEAD", None, None, 1, 1)
    assert len(page2) == 1 and not more2
    assert page1[0]["commit"] != page2[0]["commit"]
    by_path, _ = gitops.log(
        cfg, "demo", "upstream", "HEAD", "debian/demo.init", None, 20, 0
    )
    assert len(by_path) == 2  # the add and the delete
    by_grep, _ = gitops.log(cfg, "demo", "upstream", "HEAD", None, "drop SysV", 20, 0)
    assert len(by_grep) == 1


def test_show_file_windowing(cfg):
    gitops.sync(cfg, "demo", "upstream")
    chunk, total, has_more = gitops.show_file(
        cfg, "demo", "upstream", "README.md", "HEAD", 400, 0
    )
    assert chunk == "hello fixture" and total == 1 and not has_more
    # The deleted init script is still readable at the first commit.
    chunk, total, has_more = gitops.show_file(
        cfg, "demo", "upstream", "debian/demo.init", "HEAD~1", 1, 0
    )
    assert chunk == "#!/bin/sh" and total == 2 and has_more


def test_show_file_missing_is_error(cfg):
    gitops.sync(cfg, "demo", "upstream")
    with pytest.raises(GitOpsError, match="failed"):
        gitops.show_file(cfg, "demo", "upstream", "debian/demo.init", "HEAD", 400, 0)


def test_list_tree(cfg):
    gitops.sync(cfg, "demo", "upstream")
    root = gitops.list_tree(cfg, "demo", "upstream", "", "HEAD")
    names = {e["path"]: e["type"] for e in root}
    assert names["README.md"] == "blob"
    assert names["debian"] == "tree"
    sub = gitops.list_tree(cfg, "demo", "upstream", "debian", "HEAD")
    assert [e["path"] for e in sub] == ["debian/control"]


def test_grep(cfg):
    gitops.sync(cfg, "demo", "upstream")
    matches, has_more = gitops.grep(
        cfg, "demo", "upstream", "hello", "HEAD", None, 50, 0
    )
    assert not has_more
    assert matches == [{"path": "README.md", "line": 1, "content": "hello fixture"}]
    none, _ = gitops.grep(cfg, "demo", "upstream", "absent-string", "HEAD", None, 50, 0)
    assert none == []


def test_find_init_scripts_and_the_drop_story(cfg):
    gitops.sync(cfg, "demo", "upstream")
    # At HEAD the init script is gone; the systemd unit remains.
    now = gitops.find_init_scripts(cfg, "demo", "upstream", "HEAD")
    assert {f["path"] for f in now} == {"systemd/demo.service"}
    # One ref earlier, the SysV script is there — the archaeology answer.
    then = gitops.find_init_scripts(cfg, "demo", "upstream", "HEAD~1")
    kinds = {f["path"]: f["kind"] for f in then}
    assert kinds["debian/demo.init"] == "sysv-init"
    assert kinds["systemd/demo.service"] == "systemd-unit"
