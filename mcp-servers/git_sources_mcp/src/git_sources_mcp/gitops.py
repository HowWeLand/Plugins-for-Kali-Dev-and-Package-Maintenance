"""All git execution lives here — the only module that invokes git.

Hardening enforced at this single layer (design doc §4):
- the binary is pinned to /usr/bin/git (ground rule 5, no $PATH resolution);
- arguments are passed as a list to subprocess — no shell ever parses them;
- the environment is rebuilt from scratch: no inherited GIT_* variables, and
  GIT_TERMINAL_PROMPT=0 so a misconfigured remote fails instead of hanging
  the server waiting for credentials that don't exist;
- every clone path is resolved and checked to sit under the workdir;
- refs and in-repo paths are refused if they could be parsed as options.

Functions here are synchronous on purpose: subprocess.run is simple to read
and to test. The async tool layer calls them via asyncio.to_thread.
"""
from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import REMOTES, Config, PackageSource

GIT = "/usr/bin/git"
SYNC_TIMEOUT = 900  # seconds — full clones of wlroots-sized repos take a while
QUERY_TIMEOUT = 60


class GitOpsError(Exception):
    """Raised with a message written to be actionable for the caller."""


@dataclass(frozen=True)
class RepoRef:
    """A validated (package, remote) pair and where its clone lives."""

    package: PackageSource
    remote: str
    url: str
    path: Path

    @property
    def synced(self) -> bool:
        return (self.path / ".git").exists()


@dataclass(frozen=True)
class SyncResult:
    action: str  # "cloned" | "fetched"
    tip_before: str | None
    tip_after: str
    submodule_urls: list[str]


def resolve_repo(cfg: Config, package_name: str, remote: str) -> RepoRef:
    """The single gate every tool goes through: name -> validated repo.

    Raises GitOpsError (never returns a guess) when the package is not
    allowlisted, the remote kind is unknown, or the package has no such
    remote configured.
    """
    if remote not in REMOTES:
        raise GitOpsError(
            f"Unknown remote '{remote}'; valid remotes are: {', '.join(REMOTES)}."
        )
    pkg = cfg.packages.get(package_name)
    if pkg is None:
        raise GitOpsError(
            f"'{package_name}' is not in the allowlist. Run gitsrc_list_packages "
            f"to see permitted packages; additions require a reviewed change to "
            f"{cfg.path}."
        )
    url = pkg.url_for(remote)
    if url is None:
        have = [r for r in REMOTES if pkg.url_for(r)]
        raise GitOpsError(
            f"'{package_name}' has no {remote} remote configured "
            f"(it has: {', '.join(have)})."
        )
    workdir = cfg.workdir.resolve()
    path = (workdir / package_name / remote).resolve()
    # Belt-and-braces: the name regex already forbids separators, but the
    # containment check must hold even if that ever changes.
    if not path.is_relative_to(workdir):
        raise GitOpsError(f"Refusing path outside workdir: {path}")
    return RepoRef(package=pkg, remote=remote, url=url, path=path)


def require_synced(repo: RepoRef) -> RepoRef:
    if not repo.synced:
        raise GitOpsError(
            f"'{repo.package.name}' ({repo.remote}) is not synced yet — run "
            f"gitsrc_sync with package='{repo.package.name}', "
            f"remote='{repo.remote}' first."
        )
    return repo


def safe_ref(ref: str) -> str:
    """Refuse refs that git would parse as command-line options."""
    if not ref or ref.startswith("-"):
        raise GitOpsError(f"Invalid ref {ref!r}: refs may not start with '-'.")
    return ref


def safe_repo_path(path: str) -> str:
    """Refuse in-repo paths that escape the repo or look like options."""
    if path.startswith(("-", "/")) or ".." in Path(path).parts:
        raise GitOpsError(
            f"Invalid path {path!r}: repo paths must be relative, must not "
            "start with '-', and must not contain '..'."
        )
    return path


def _env(cfg: Config) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(cfg.workdir),
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C.UTF-8",
    }


def run_git(
    cfg: Config,
    args: list[str],
    timeout: int = QUERY_TIMEOUT,
    ok_returncodes: tuple[int, ...] = (0,),
) -> str:
    """Run git with pinned binary, clean environment, and no shell."""
    try:
        proc = subprocess.run(
            [GIT, *args],
            env=_env(cfg),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise GitOpsError(
            f"git {args[0]} exceeded {timeout}s. For sync of a large repo, "
            "retry — clone resumes from scratch but fetch is incremental."
        ) from None
    except FileNotFoundError:
        raise GitOpsError(f"git binary not found at {GIT}.") from None
    if proc.returncode not in ok_returncodes:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise GitOpsError(f"git {args[0]} failed: {detail[:500]}")
    return proc.stdout


def sync(cfg: Config, package_name: str, remote: str) -> SyncResult:
    """Clone (first time) or fast-forward fetch (after) one repo.

    The only function here that touches the network. Fetch is --ff-only:
    we never author local commits, so a non-fast-forward means upstream
    rewrote history — surfaced as an error telling the caller how to recover
    rather than silently resetting.
    """
    repo = resolve_repo(cfg, package_name, remote)
    if not repo.synced:
        repo.path.parent.mkdir(parents=True, exist_ok=True)
        args = ["clone"]
        if repo.package.submodules:
            args.append("--recurse-submodules")
        args += ["--", repo.url, str(repo.path)]
        run_git(cfg, args, timeout=SYNC_TIMEOUT)
        tip_before = None
        action = "cloned"
    else:
        tip_before = run_git(
            cfg, ["-C", str(repo.path), "rev-parse", "HEAD"]
        ).strip()
        try:
            run_git(
                cfg,
                ["-C", str(repo.path), "pull", "--ff-only", "--tags", "origin"],
                timeout=SYNC_TIMEOUT,
            )
        except GitOpsError as e:
            raise GitOpsError(
                f"{e} — if upstream force-pushed, delete {repo.path} and "
                "re-run gitsrc_sync to re-clone."
            ) from None
        if repo.package.submodules:
            run_git(
                cfg,
                ["-C", str(repo.path), "submodule", "update", "--init", "--recursive"],
                timeout=SYNC_TIMEOUT,
            )
        action = "fetched"
    tip_after = run_git(cfg, ["-C", str(repo.path), "rev-parse", "HEAD"]).strip()
    return SyncResult(
        action=action,
        tip_before=tip_before,
        tip_after=tip_after,
        submodule_urls=_submodule_urls(cfg, repo),
    )


def _submodule_urls(cfg: Config, repo: RepoRef) -> list[str]:
    """Report which submodule URLs a sync actually pulled (design doc §4:
    submodules delegate a hop of trust to upstream's .gitmodules — keep
    that delegation visible)."""
    if not (repo.path / ".gitmodules").exists():
        return []
    out = run_git(
        cfg,
        [
            "config", "--file", str(repo.path / ".gitmodules"),
            "--get-regexp", r"submodule\..*\.url",
        ],
        ok_returncodes=(0, 1),  # 1 = no matches
    )
    return [line.split(None, 1)[1] for line in out.splitlines() if " " in line]


def status(cfg: Config) -> list[dict]:
    """Per-package sync state for gitsrc_list_packages."""
    rows = []
    for name, pkg in sorted(cfg.packages.items()):
        remotes = {}
        for remote in REMOTES:
            if not pkg.url_for(remote):
                continue
            repo = resolve_repo(cfg, name, remote)
            entry: dict = {"synced": repo.synced}
            if repo.synced:
                head = repo.path / ".git" / "FETCH_HEAD"
                if not head.exists():
                    head = repo.path / ".git" / "HEAD"
                entry["last_synced"] = datetime.fromtimestamp(
                    head.stat().st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds")
            remotes[remote] = entry
        rows.append(
            {"package": name, "submodules": pkg.submodules, "remotes": remotes}
        )
    return rows


def log(
    cfg: Config,
    package_name: str,
    remote: str,
    ref: str,
    path: str | None,
    grep: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], bool]:
    """Commit history; returns (entries, has_more)."""
    repo = require_synced(resolve_repo(cfg, package_name, remote))
    args = [
        "-C", str(repo.path), "log", safe_ref(ref),
        f"--max-count={limit + 1}", f"--skip={offset}",
        "--date=iso-strict", "--format=%H%x1f%an%x1f%ad%x1f%s",
    ]
    if grep:
        args.append(f"--grep={grep}")
    if path:
        args += ["--", safe_repo_path(path)]
    out = run_git(cfg, args)
    entries = []
    for line in out.splitlines():
        commit, author, date, subject = line.split("\x1f", 3)
        entries.append(
            {"commit": commit, "author": author, "date": date, "subject": subject}
        )
    has_more = len(entries) > limit
    return entries[:limit], has_more


def show_file(
    cfg: Config,
    package_name: str,
    remote: str,
    path: str,
    ref: str,
    limit_lines: int,
    offset_lines: int,
) -> tuple[str, int, bool]:
    """One file at a ref; returns (chunk, total_lines, has_more)."""
    repo = require_synced(resolve_repo(cfg, package_name, remote))
    out = run_git(
        cfg,
        ["-C", str(repo.path), "show", f"{safe_ref(ref)}:{safe_repo_path(path)}"],
    )
    lines = out.splitlines()
    chunk = lines[offset_lines : offset_lines + limit_lines]
    has_more = len(lines) > offset_lines + limit_lines
    return "\n".join(chunk), len(lines), has_more


def list_tree(
    cfg: Config, package_name: str, remote: str, path: str, ref: str
) -> list[dict]:
    """Non-recursive directory listing at a ref."""
    repo = require_synced(resolve_repo(cfg, package_name, remote))
    args = ["-C", str(repo.path), "ls-tree", "--long", safe_ref(ref)]
    if path:
        # Trailing slash asks git for the directory's contents, not the
        # directory entry itself.
        args += ["--", safe_repo_path(path).rstrip("/") + "/"]
    out = run_git(cfg, args)
    entries = []
    for line in out.splitlines():
        meta, name = line.split("\t", 1)
        _mode, otype, _obj, size = meta.split()
        entries.append(
            {
                "path": name,
                "type": otype,  # "blob" (file) or "tree" (directory)
                "size": None if size == "-" else int(size),
            }
        )
    return entries


def grep(
    cfg: Config,
    package_name: str,
    remote: str,
    pattern: str,
    ref: str,
    path_glob: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], bool]:
    """git grep at a ref; returns (matches, has_more)."""
    repo = require_synced(resolve_repo(cfg, package_name, remote))
    args = ["-C", str(repo.path), "grep", "-n", "-I", "-e", pattern, safe_ref(ref)]
    if path_glob:
        args += ["--", safe_repo_path(path_glob)]
    out = run_git(cfg, args, ok_returncodes=(0, 1))  # 1 = no matches
    matches = []
    for line in out.splitlines():
        # Format: <ref>:<path>:<lineno>:<content>
        try:
            _ref, fpath, lineno, content = line.split(":", 3)
        except ValueError:
            continue
        matches.append({"path": fpath, "line": int(lineno), "content": content})
    has_more = len(matches) > offset + limit
    return matches[offset : offset + limit], has_more


# Path patterns that identify init/service material, by init system.
# Classification is by path only — cheap and good enough to orient; read the
# file via gitsrc_show_file to confirm.
_INIT_PATTERNS: list[tuple[str, str]] = [
    ("debian/*.init", "sysv-init"),
    ("debian/*.init.d", "sysv-init"),
    ("*init.d/*", "sysv-init"),
    ("debian/*.service", "systemd-unit"),
    ("*.service", "systemd-unit"),
    ("*.socket", "systemd-unit"),
    ("*.timer", "systemd-unit"),
    ("*openrc*", "openrc"),
    ("*.initd", "openrc"),
    ("*conf.d/*", "openrc-or-sysv-confd"),
]


def find_init_scripts(
    cfg: Config, package_name: str, remote: str, ref: str
) -> list[dict]:
    """Sweep the whole tree at a ref for init/service material (design doc §5:
    the one workflow tool, because 'did this package ever ship an init script'
    is *the* recurring Project-1 question)."""
    repo = require_synced(resolve_repo(cfg, package_name, remote))
    out = run_git(
        cfg, ["-C", str(repo.path), "ls-tree", "-r", "--name-only", safe_ref(ref)]
    )
    found = []
    for name in out.splitlines():
        for pattern, kind in _INIT_PATTERNS:
            if fnmatch.fnmatch(name, pattern):
                found.append({"path": name, "kind": kind})
                break
    return found
