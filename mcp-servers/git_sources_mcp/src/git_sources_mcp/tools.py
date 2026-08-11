"""Tool definitions: the surface the AI clients see.

Each @mcp.tool function's docstring becomes the tool description, and the
Pydantic model becomes its JSON Schema — the model-facing contract is
generated from exactly what this file says (design doc §5). All validation
lives in the models (extra='forbid' rejects unknown fields); all git work
lives in gitops; this layer only translates and formats.
"""
from __future__ import annotations

import asyncio
import json
from enum import Enum

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from . import gitops
from .config import Config
from .gitops import GitOpsError

mcp = MCPServer("git_sources_mcp")

# Set once at startup by __main__ before mcp.run(); tools fail loudly if not.
_cfg: Config | None = None


def init_state(cfg: Config) -> None:
    global _cfg
    _cfg = cfg


def _config() -> Config:
    if _cfg is None:  # pragma: no cover - only reachable if wiring breaks
        raise GitOpsError("Server not initialized with a config; this is a bug.")
    return _cfg


class Remote(str, Enum):
    UPSTREAM = "upstream"
    SALSA = "salsa"


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class _RepoBase(_Base):
    package: str = Field(
        ...,
        description="Package name from gitsrc_list_packages, e.g. 'wayfire'",
        min_length=1,
        max_length=100,
    )
    remote: Remote = Field(
        Remote.UPSTREAM, description="'upstream' or 'salsa' (Debian packaging repo)"
    )


class ListPackagesInput(_Base):
    response_format: ResponseFormat = ResponseFormat.MARKDOWN


class SyncInput(_RepoBase):
    response_format: ResponseFormat = ResponseFormat.MARKDOWN


class LogInput(_RepoBase):
    ref: str = Field("HEAD", description="Branch, tag, or commit", max_length=200)
    path: str | None = Field(
        None, description="Limit history to this repo-relative path, e.g. 'debian/'"
    )
    grep: str | None = Field(
        None, description="Only commits whose message matches this pattern"
    )
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0, description="Commits to skip, for pagination")
    response_format: ResponseFormat = ResponseFormat.MARKDOWN


class ShowFileInput(_RepoBase):
    path: str = Field(
        ..., description="Repo-relative file path, e.g. 'debian/control'"
    )
    ref: str = Field("HEAD", description="Branch, tag, or commit", max_length=200)
    limit_lines: int = Field(400, ge=1, le=2000)
    offset_lines: int = Field(0, ge=0, description="Lines to skip, for large files")


class ListTreeInput(_RepoBase):
    path: str = Field(
        "", description="Repo-relative directory ('' for the repo root)"
    )
    ref: str = Field("HEAD", description="Branch, tag, or commit", max_length=200)
    response_format: ResponseFormat = ResponseFormat.MARKDOWN


class GrepInput(_RepoBase):
    pattern: str = Field(
        ..., description="Regex passed to git grep", min_length=1, max_length=500
    )
    ref: str = Field("HEAD", description="Branch, tag, or commit", max_length=200)
    path_glob: str | None = Field(
        None, description="Limit to paths matching this glob, e.g. 'debian/*'"
    )
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
    response_format: ResponseFormat = ResponseFormat.MARKDOWN


class FindInitScriptsInput(_RepoBase):
    ref: str = Field("HEAD", description="Branch, tag, or commit", max_length=200)
    response_format: ResponseFormat = ResponseFormat.MARKDOWN


def _err(e: Exception) -> str:
    return f"Error: {e}"


def _paginated(items: list, has_more: bool, offset: int, key: str) -> str:
    return json.dumps(
        {
            "count": len(items),
            "offset": offset,
            "has_more": has_more,
            "next_offset": offset + len(items) if has_more else None,
            key: items,
        },
        indent=2,
    )


@mcp.tool(
    name="gitsrc_list_packages",
    annotations=ToolAnnotations(
        title="List allowlisted packages",
        read_only_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def gitsrc_list_packages(params: ListPackagesInput) -> str:
    """List the packages this server is permitted to reach, and their state.

    The discovery entry point: shows each allowlisted package, which remotes
    it has (upstream / salsa), whether each remote is synced locally, and
    when it was last synced. Packages not listed here are not reachable by
    any tool — additions require a reviewed change to sources.toml.
    """
    try:
        rows = await asyncio.to_thread(gitops.status, _config())
    except (GitOpsError, OSError) as e:
        return _err(e)
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"count": len(rows), "packages": rows}, indent=2)
    lines = [f"# Allowlisted packages ({len(rows)})", ""]
    for row in rows:
        lines.append(f"## {row['package']}" + ("  (submodules)" if row["submodules"] else ""))
        for remote, entry in row["remotes"].items():
            state = (
                f"synced, last {entry['last_synced']}"
                if entry["synced"]
                else "not synced — run gitsrc_sync"
            )
            lines.append(f"- **{remote}**: {state}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool(
    name="gitsrc_sync",
    annotations=ToolAnnotations(
        title="Sync (clone/fetch) a package's repo",
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def gitsrc_sync(params: SyncInput) -> str:
    """Clone (first time) or fetch (after) one allowlisted package's repo.

    The only tool that touches the network. Writes only inside the
    configured workdir; remotes are credential-less https, so the server is
    structurally unable to push. When the package declares submodules, the
    clone recurses into them and the result reports which submodule URLs
    were pulled, so that delegation of trust stays visible.
    """
    try:
        result = await asyncio.to_thread(
            gitops.sync, _config(), params.package, params.remote.value
        )
    except GitOpsError as e:
        return _err(e)
    payload = {
        "package": params.package,
        "remote": params.remote.value,
        "action": result.action,
        "tip_before": result.tip_before,
        "tip_after": result.tip_after,
        "submodule_urls": result.submodule_urls,
    }
    if params.response_format == ResponseFormat.JSON:
        return json.dumps(payload, indent=2)
    lines = [
        f"{result.action}: {params.package} ({params.remote.value})",
        f"- tip before: {result.tip_before or '(fresh clone)'}",
        f"- tip after:  {result.tip_after}",
    ]
    if result.submodule_urls:
        lines.append("- submodules pulled:")
        lines += [f"  - {u}" for u in result.submodule_urls]
    return "\n".join(lines)


@mcp.tool(
    name="gitsrc_log",
    annotations=ToolAnnotations(
        title="Commit history",
        read_only_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def gitsrc_log(params: LogInput) -> str:
    """Commit history for an allowlisted, already-synced repo.

    Supports a path filter (e.g. 'debian/' to see only packaging changes), a
    commit-message grep, and offset/limit pagination. Typical archaeology
    move: gitsrc_log with path='debian/foo.init' shows every commit that
    touched an init script, including the one that deleted it.
    """
    try:
        entries, has_more = await asyncio.to_thread(
            gitops.log,
            _config(),
            params.package,
            params.remote.value,
            params.ref,
            params.path,
            params.grep,
            params.limit,
            params.offset,
        )
    except GitOpsError as e:
        return _err(e)
    if params.response_format == ResponseFormat.JSON:
        return _paginated(entries, has_more, params.offset, "commits")
    if not entries:
        return f"No commits found (ref={params.ref}, path={params.path}, grep={params.grep})."
    lines = [f"# {params.package} ({params.remote.value}) log @ {params.ref}", ""]
    for e in entries:
        lines.append(f"- `{e['commit'][:12]}` {e['date']} {e['author']}: {e['subject']}")
    if has_more:
        lines.append("")
        lines.append(f"(more available — re-run with offset={params.offset + len(entries)})")
    return "\n".join(lines)


@mcp.tool(
    name="gitsrc_show_file",
    annotations=ToolAnnotations(
        title="Show one file at a ref",
        read_only_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def gitsrc_show_file(params: ShowFileInput) -> str:
    """Content of one file at a ref (HEAD by default) from a synced repo.

    Large files are windowed by limit_lines/offset_lines rather than silently
    truncated: the header always states total lines and whether more remain.
    """
    try:
        chunk, total, has_more = await asyncio.to_thread(
            gitops.show_file,
            _config(),
            params.package,
            params.remote.value,
            params.path,
            params.ref,
            params.limit_lines,
            params.offset_lines,
        )
    except GitOpsError as e:
        return _err(e)
    header = (
        f"# {params.path} @ {params.ref} "
        f"(lines {params.offset_lines + 1}-{params.offset_lines + params.limit_lines} "
        f"of {total})"
        if has_more or params.offset_lines
        else f"# {params.path} @ {params.ref} ({total} lines)"
    )
    tail = (
        f"\n\n(more — re-run with offset_lines={params.offset_lines + params.limit_lines})"
        if has_more
        else ""
    )
    return f"{header}\n\n```\n{chunk}\n```{tail}"


@mcp.tool(
    name="gitsrc_list_tree",
    annotations=ToolAnnotations(
        title="List a directory at a ref",
        read_only_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def gitsrc_list_tree(params: ListTreeInput) -> str:
    """Non-recursive directory listing at a ref — orientation before
    gitsrc_show_file or gitsrc_grep. Entries are 'blob' (file) or 'tree'
    (directory)."""
    try:
        entries = await asyncio.to_thread(
            gitops.list_tree,
            _config(),
            params.package,
            params.remote.value,
            params.path,
            params.ref,
        )
    except GitOpsError as e:
        return _err(e)
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"count": len(entries), "entries": entries}, indent=2)
    if not entries:
        return f"Nothing at '{params.path or '/'}' @ {params.ref}."
    lines = [f"# {params.package}:{params.path or '/'} @ {params.ref}", ""]
    for e in entries:
        marker = "/" if e["type"] == "tree" else ""
        size = f"  ({e['size']} bytes)" if e["size"] is not None else ""
        lines.append(f"- {e['path']}{marker}{size}")
    return "\n".join(lines)


@mcp.tool(
    name="gitsrc_grep",
    annotations=ToolAnnotations(
        title="Search file contents at a ref",
        read_only_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def gitsrc_grep(params: GrepInput) -> str:
    """git grep across a synced repo at a ref: regex pattern, optional path
    glob, offset/limit pagination. Binary files are skipped."""
    try:
        matches, has_more = await asyncio.to_thread(
            gitops.grep,
            _config(),
            params.package,
            params.remote.value,
            params.pattern,
            params.ref,
            params.path_glob,
            params.limit,
            params.offset,
        )
    except GitOpsError as e:
        return _err(e)
    if params.response_format == ResponseFormat.JSON:
        return _paginated(matches, has_more, params.offset, "matches")
    if not matches:
        return f"No matches for {params.pattern!r} @ {params.ref}."
    lines = [f"# grep {params.pattern!r} in {params.package} @ {params.ref}", ""]
    for m in matches:
        lines.append(f"- `{m['path']}:{m['line']}`: {m['content'].strip()}")
    if has_more:
        lines.append("")
        lines.append(f"(more available — re-run with offset={params.offset + len(matches)})")
    return "\n".join(lines)


@mcp.tool(
    name="gitsrc_find_init_scripts",
    annotations=ToolAnnotations(
        title="Find init/service material in a repo",
        read_only_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def gitsrc_find_init_scripts(params: FindInitScriptsInput) -> str:
    """Sweep a synced repo at a ref for init-system material: SysV init
    scripts (debian/*.init, init.d/), systemd units (*.service, *.socket,
    *.timer), and OpenRC scripts (*.initd, openrc dirs).

    Classification is by path pattern only — confirm by reading the file.
    To find *when* something disappeared, follow up with gitsrc_log using
    the reported path.
    """
    try:
        found = await asyncio.to_thread(
            gitops.find_init_scripts,
            _config(),
            params.package,
            params.remote.value,
            params.ref,
        )
    except GitOpsError as e:
        return _err(e)
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"count": len(found), "matches": found}, indent=2)
    if not found:
        return (
            f"No init/service material found in {params.package} "
            f"({params.remote.value}) @ {params.ref}. If this package should "
            "have shipped one historically, try an older ref or "
            "gitsrc_log with grep='init'."
        )
    lines = [f"# init/service material in {params.package} @ {params.ref}", ""]
    for f in found:
        lines.append(f"- `{f['path']}` — {f['kind']}")
    return "\n".join(lines)
