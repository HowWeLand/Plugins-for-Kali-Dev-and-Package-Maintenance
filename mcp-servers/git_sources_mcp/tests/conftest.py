"""Shared fixtures: a local fixture git repo, built offline in tmp_path.

Tests construct Config/PackageSource dataclasses directly with a local-path
"URL" — deliberately bypassing load_config's https-only rule, which is
enforced at the loader boundary (and tested in test_config.py). gitops
itself must work with whatever validated config it is handed.
"""
import subprocess

import pytest

from git_sources_mcp.config import Config, PackageSource

GIT = "/usr/bin/git"


def git(*args, cwd):
    subprocess.run(
        [GIT, "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def fixture_repo(tmp_path):
    """A small history: v1 ships a SysV init script, v2 deletes it."""
    src = tmp_path / "origin"
    src.mkdir()
    git("init", "-b", "main", cwd=src)
    (src / "README.md").write_text("hello fixture\n")
    debian = src / "debian"
    debian.mkdir()
    (debian / "demo.init").write_text("#!/bin/sh\n# SysV init script\n")
    (debian / "control").write_text("Source: demo\n")
    unit = src / "systemd"
    unit.mkdir()
    (unit / "demo.service").write_text("[Unit]\nDescription=demo\n")
    git("add", "-A", cwd=src)
    git("commit", "-m", "initial release with init script", cwd=src)
    git("rm", "debian/demo.init", cwd=src)
    git("commit", "-m", "drop SysV init script for systemd", cwd=src)
    return src


@pytest.fixture
def cfg(tmp_path, fixture_repo):
    return Config(
        path=tmp_path / "sources.toml",
        workdir=tmp_path / "work",
        packages={
            "demo": PackageSource(name="demo", upstream=str(fixture_repo)),
        },
    )
