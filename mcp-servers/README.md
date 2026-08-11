# mcp-servers

MCP servers exposing scoped access to knowledge sources: upstream git, Salsa, and the Debian BTS — each bound to an explicit allowlist of named repos/packages (ground rule 6).

Servers:

- `git_sources_mcp/` — scoped, read-only access to allowlisted upstream/Salsa
  git repos. See `docs/design-git-sources-mcp.md` for the design.
