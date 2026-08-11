"""Load and validate the sources.toml allowlist.

This file is the capability grant (design doc §4): tools accept package
*names*, and this module is the only place a name resolves to a URL. If a
package is not in the file loaded here, no tool can reach it — there is
nothing to bypass, because the URL never crosses the tool boundary.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# The two remote kinds a package may declare. Tool inputs validate against
# this same tuple, so an unknown remote is rejected before any lookup.
REMOTES = ("upstream", "salsa")

# Debian source-package name charset (Policy §5.6.1): lowercase alphanumerics
# plus . + - , starting alphanumeric. No slashes, so a package name can never
# be a path component attack; length-capped for sanity.
_PACKAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,99}$")

_ALLOWED_PACKAGE_KEYS = {"upstream", "salsa", "submodules"}


class ConfigError(Exception):
    """sources.toml is missing, malformed, or violates an allowlist rule."""


@dataclass(frozen=True)
class PackageSource:
    """One allowlisted package: its name and the remotes it may be pulled from."""

    name: str
    upstream: str | None = None
    salsa: str | None = None
    submodules: bool = False

    def url_for(self, remote: str) -> str | None:
        if remote not in REMOTES:
            raise ConfigError(
                f"Unknown remote kind '{remote}'; valid remotes are: {', '.join(REMOTES)}."
            )
        return self.upstream if remote == "upstream" else self.salsa


@dataclass(frozen=True)
class Config:
    """The loaded allowlist: where clones live, and what may be cloned."""

    path: Path
    workdir: Path
    packages: dict[str, PackageSource] = field(default_factory=dict)


def _require_https(package: str, remote: str, url: object) -> str:
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ConfigError(
            f"packages.{package}.{remote}: only https:// remotes are allowed "
            f"(got {url!r}). Credential-less https is what makes the server "
            "structurally unable to push (design doc §4)."
        )
    return url


def load_config(path: str | Path) -> Config:
    """Parse and validate sources.toml, rejecting anything out of contract.

    Absolute paths are required for both the config file and the workdir
    (ground rule 5) — a relative path would silently depend on the client's
    working directory, which differs per client.
    """
    p = Path(path)
    if not p.is_absolute():
        raise ConfigError(f"Config path must be absolute (got '{p}').")
    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(
            f"Config file not found: {p}. Copy sources.example.toml there and "
            "list the packages this server may reach."
        ) from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Config file {p} is not valid TOML: {e}") from None

    workdir = raw.get("workdir")
    if not isinstance(workdir, str) or not Path(workdir).is_absolute():
        raise ConfigError(
            f"'workdir' must be an absolute path string (got {workdir!r})."
        )

    packages_raw = raw.get("packages")
    if not isinstance(packages_raw, dict) or not packages_raw:
        raise ConfigError(
            "No [packages.*] entries found. The allowlist must name at least "
            "one package; an empty allowlist grants nothing."
        )

    packages: dict[str, PackageSource] = {}
    for name, entry in packages_raw.items():
        if not _PACKAGE_NAME_RE.match(name):
            raise ConfigError(
                f"Invalid package name '{name}': must match Debian source "
                "package charset [a-z0-9][a-z0-9.+-]* (no slashes, no uppercase)."
            )
        if not isinstance(entry, dict):
            raise ConfigError(f"packages.{name} must be a table.")
        unknown = set(entry) - _ALLOWED_PACKAGE_KEYS
        if unknown:
            raise ConfigError(
                f"packages.{name} has unknown key(s) {sorted(unknown)}; "
                f"allowed keys: {sorted(_ALLOWED_PACKAGE_KEYS)}."
            )
        upstream = entry.get("upstream")
        salsa = entry.get("salsa")
        if upstream is None and salsa is None:
            raise ConfigError(
                f"packages.{name} declares no remotes; give it 'upstream' "
                "and/or 'salsa', or remove the entry."
            )
        if upstream is not None:
            upstream = _require_https(name, "upstream", upstream)
        if salsa is not None:
            salsa = _require_https(name, "salsa", salsa)
        submodules = entry.get("submodules", False)
        if not isinstance(submodules, bool):
            raise ConfigError(f"packages.{name}.submodules must be true or false.")
        packages[name] = PackageSource(
            name=name, upstream=upstream, salsa=salsa, submodules=submodules
        )

    return Config(path=p, workdir=Path(workdir), packages=packages)
