# Plugins for Kali Dev and Package Maintenance

Tooling home for a multi-project effort around Kali Linux packaging and init-system work.
This repo holds the **plugins, MCP servers, skills, and agent definitions** that the AI
collaborators on the effort (Claude Code, Claude chat, ChatGPT, Gemini Code Assist) use to
do that work — scoped, auditable, and reviewable in one place.

This is "Project 4" of the wider effort: rather than working ad hoc across the packaging
projects below, build proper tooling scoped to the packages Jay maintains or wants to
maintain upstream — the MATE stack, Wayfire, Cinnamon, and whatever OpenRC-adjacent
packages come out of Project 1.

## The wider effort

| # | Project | Summary |
|---|---------|---------|
| 1 | **OpenRC conversion** | Convert a live Kali system from systemd to OpenRC and get it back to fully functioning; end state is a metapackage (deps + apt pinning + replacement service files, Devuan-first sourcing with Gentoo/Artix fallback). |
| 2 | **MATE polish + Wayland/Wayfire** | Personal config/metapackage for MATE theming (dogfood first, PR to `kali-themes`/`kali-defaults`/`kali-default-desktops` once proven), plus independent packaging of MATE's Wayfire-based Wayland session. |
| 3 | **kali-desktop-cinnamon** | New `kali-desktop-<de>` metapackage following Kali's existing convention. Earliest stage. |
| 4 | **This repo** | The tooling layer serving projects 1–3. |

Team lanes: Claude (chat) handles planning/architecture and this plugin's design; ChatGPT
does hands-on Kali packaging; Google Cloud/BigQuery runs the large-scale systemd
surface-area analysis; Gemini Code Assist does package archaeology (Devuan/Gentoo/Artix
service-file mining); Claude Code assists on the plugin/MCP dev work here.

## What lives here

```
plugins/       Claude Code plugin(s) bundling the pieces below
mcp-servers/   MCP servers exposing scoped access to knowledge sources
skills/        Skills for recurring packaging workflows
agents/        Agent (subagent) definitions for delegated tasks
knowledge/     Shared per-package findings (archaeology, BTS, provenance) — see knowledge/README.md
docs/          Design notes, decisions, provenance conventions
```

### Knowledge sources — bound explicitly, per package

Sources are bound by *naming* what a tool may reach, never by granting general fetch
access. The binding mechanism matches each source's freshness needs:

- **Upstream git** — read-only pull into a sandboxed workdir, scoped to named repos only.
- **Salsa** (Debian's GitLab) — same scoping approach.
- **Debian BTS** — wrap existing tooling (`debbugs` / `querybts` / the BTS SOAP
  interface) rather than build a bespoke scraper, scoped to the tracked packages.

These are *living* sources: they stay current via scoped live access, not frozen
snapshots — staleness would defeat the purpose. Static reference material (man pages,
doc-base) instead lives directly in the build environment and needs no fetch tooling.

## Ground rules

These hold across every tool in this repo (see `CLAUDE.md` for the working version):

1. **Least privilege by default** — scope every tool, account, and sudoers rule to the
   exact capability needed.
2. **Prefer reversible actions** — open a PR, don't merge; produce a report, don't
   mutate, unless the action is narrow and already vetted.
3. **Unattended automation must be fixed and human-vetted beforehand** — an AI never
   authors and executes unsupervised automation in the same breath.
4. **Elevated rights are scoped at the OS level** — dedicated `nologin` service account,
   sudoers pinned to one absolute path, root-owned non-writable script, `env_reset`,
   retained sudo logging.
5. **Absolute paths everywhere** — never rely on `$PATH` resolution.
6. **Bind knowledge sources explicitly** — named repos/packages, not general crawl.
7. **Sandbox at the cheapest sufficient tier** — scoped-home user → namespace isolation
   (bubblewrap/firejail/nspawn) → full VM. Generous freedom inside, minimal at the
   boundary.
8. **Track provenance, not just correctness** — where a service file, patch, or config
   came from (Kali / Devuan / Gentoo / Artix / newly written) stays queryable via
   apt-tag, not buried in script headers.

## Status

Scaffolding. No plugin, server, skill, or agent implementations yet — structure and
conventions first, reviewed by PR before anything executable lands.
