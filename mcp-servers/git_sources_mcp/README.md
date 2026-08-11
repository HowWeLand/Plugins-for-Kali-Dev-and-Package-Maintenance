# git_sources_mcp

Scoped, read-only MCP access to allowlisted git repos (upstream + Salsa).
Design: [`docs/design-git-sources-mcp.md`](../../docs/design-git-sources-mcp.md).

The one-sentence security model: **tools take package names, never URLs** — the
name→URL mapping lives only in `sources.toml`, so no generic fetch capability
exists, and every write is confined to the configured workdir.

## Setup

```sh
/usr/bin/python3 -m venv /home/user1138/Projects/kali-mate-dev/venv
/home/user1138/Projects/kali-mate-dev/venv/bin/pip install /path/to/this/repo/mcp-servers/git_sources_mcp
cp sources.example.toml /home/user1138/Projects/kali-mate-dev/sources.toml
# then edit sources.toml — each entry is a capability grant
```

## Client registration

One stdio server, three clients — same shape everywhere (absolute paths, per
ground rule 5):

```jsonc
// Claude Code — .mcp.json
{
  "mcpServers": {
    "git-sources": {
      "command": "/home/user1138/Projects/kali-mate-dev/venv/bin/python",
      "args": ["-m", "git_sources_mcp", "--config", "/home/user1138/Projects/kali-mate-dev/sources.toml"]
    }
  }
}
```

```toml
# Codex CLI — ~/.codex/config.toml
[mcp_servers.git-sources]
command = "/home/user1138/Projects/kali-mate-dev/venv/bin/python"
args = ["-m", "git_sources_mcp", "--config", "/home/user1138/Projects/kali-mate-dev/sources.toml"]
```

```jsonc
// Gemini CLI — ~/.gemini/settings.json
{
  "mcpServers": {
    "git-sources": {
      "command": "/home/user1138/Projects/kali-mate-dev/venv/bin/python",
      "args": ["-m", "git_sources_mcp", "--config", "/home/user1138/Projects/kali-mate-dev/sources.toml"]
    }
  }
}
```

## Tools

| Tool | Purpose |
|------|---------|
| `gitsrc_list_packages` | What am I allowed to touch, and is it synced? |
| `gitsrc_sync` | Clone/fetch one package's remote (the only network tool) |
| `gitsrc_log` | Commit history with path/grep filters and pagination |
| `gitsrc_show_file` | One file at a ref, windowed for large files |
| `gitsrc_list_tree` | Directory listing at a ref |
| `gitsrc_grep` | Content search at a ref |
| `gitsrc_find_init_scripts` | Sweep a tree for SysV/systemd/OpenRC material |

Typical archaeology session: `gitsrc_find_init_scripts` at an old tag →
`gitsrc_log` with `path=` the reported script → `gitsrc_show_file` at the
commit before the drop.

## Tests

Offline, no network — fixture repos are built in pytest's tmp_path:

```sh
pip install -e '.[dev]'
python -m pytest
```

`tests/test_stdio_raw.py` is the teaching test: it speaks raw JSON-RPC to the
server over stdio with no SDK on the client side — read it to see exactly
what Claude Code/Codex/Gemini do under the hood.

Interactive poking: `npx @modelcontextprotocol/inspector` (a debugging UI
that lists the tools and lets you fire calls by hand).
