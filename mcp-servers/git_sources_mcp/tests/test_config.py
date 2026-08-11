"""Allowlist loader: everything out of contract is rejected with a clear error."""
import pytest

from git_sources_mcp.config import ConfigError, load_config


def write_cfg(tmp_path, body: str):
    p = tmp_path / "sources.toml"
    p.write_text(body, encoding="utf-8")
    return p


VALID = """
workdir = "/tmp/sources"

[packages.wayfire]
upstream = "https://github.com/WayfireWM/wayfire"
salsa = "https://salsa.debian.org/debian/wayfire"
submodules = true

[packages.wlroots]
upstream = "https://gitlab.freedesktop.org/wlroots/wlroots"
"""


def test_valid_config_loads(tmp_path):
    cfg = load_config(write_cfg(tmp_path, VALID))
    assert set(cfg.packages) == {"wayfire", "wlroots"}
    assert cfg.packages["wayfire"].submodules is True
    assert cfg.packages["wlroots"].submodules is False
    assert cfg.packages["wlroots"].salsa is None
    assert cfg.workdir.is_absolute()


def test_relative_config_path_rejected():
    with pytest.raises(ConfigError, match="absolute"):
        load_config("sources.toml")


def test_missing_file_actionable(tmp_path):
    with pytest.raises(ConfigError, match="sources.example.toml"):
        load_config(tmp_path / "nope.toml")


def test_relative_workdir_rejected(tmp_path):
    body = VALID.replace('"/tmp/sources"', '"sources"')
    with pytest.raises(ConfigError, match="workdir"):
        load_config(write_cfg(tmp_path, body))


def test_non_https_url_rejected(tmp_path):
    for bad in ("http://example.com/r", "git://example.com/r", "ssh://git@example.com/r"):
        body = VALID.replace("https://github.com/WayfireWM/wayfire", bad)
        with pytest.raises(ConfigError, match="https"):
            load_config(write_cfg(tmp_path, body))


def test_invalid_package_name_rejected(tmp_path):
    for bad in ("Evil", "a/b", "../escape", "-dash"):
        body = f'workdir = "/tmp/s"\n[packages."{bad}"]\nupstream = "https://x.example/r"\n'
        with pytest.raises(ConfigError, match="Invalid package name"):
            load_config(write_cfg(tmp_path, body))


def test_unknown_key_rejected(tmp_path):
    body = VALID + "\n[packages.other]\nupstream = \"https://x.example/r\"\nfetch_url = \"https://evil\"\n"
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(write_cfg(tmp_path, body))


def test_package_without_remotes_rejected(tmp_path):
    body = 'workdir = "/tmp/s"\n[packages.empty]\nsubmodules = false\n'
    with pytest.raises(ConfigError, match="no remotes"):
        load_config(write_cfg(tmp_path, body))


def test_empty_allowlist_rejected(tmp_path):
    with pytest.raises(ConfigError, match="allowlist"):
        load_config(write_cfg(tmp_path, 'workdir = "/tmp/s"\n'))
