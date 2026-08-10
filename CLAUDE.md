# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repo is

The tooling layer ("Project 4") of a multi-project Kali packaging and init-system
effort. It holds the plugins, MCP servers, skills, and agent definitions that the AI
collaborators on the effort use — including Claude Code itself. You are both a builder
and a consumer of what lives here.

The packages in scope are the ones Jay maintains or wants to maintain upstream: the
MATE stack, Wayfire, Cinnamon, and OpenRC-adjacent packages coming out of the systemd →
OpenRC conversion (Project 1). See `README.md` for the full project map and team lanes.

## Layout

```
plugins/       Claude Code plugin(s) bundling the pieces below
mcp-servers/   MCP servers exposing scoped access to knowledge sources
skills/        Skills for recurring packaging workflows
agents/        Agent (subagent) definitions for delegated tasks
knowledge/     Shared per-package findings (archaeology, BTS, provenance) — see knowledge/README.md
docs/          Design notes, decisions, provenance conventions
```

## Ground rules (engineering constraints, not suggestions)

1. **Least privilege by default.** Scope every tool, account, and sudoers rule to the
   exact capability needed — nothing broader "to be safe" or to save a round trip.
2. **Prefer reversible actions.** Open a PR, don't merge. Produce a report, don't
   mutate the filesystem directly, unless the action is narrow and already vetted.
3. **Anything that runs unattended must be fixed and human-vetted beforehand.** Never
   author and execute unsupervised automation (installer hooks, cron-like jobs) in the
   same breath — a human or a deterministic check gates execution first.
4. **When elevated rights are unavoidable, scope them at the OS level:** dedicated
   service account with shell `/bin/nologin`; sudoers rule pinned to one absolute path
   (no wildcards — argument globs are an injection vector); the script root-owned and
   **not writable by the account allowed to run it**; `Defaults env_reset` for that
   entry; confirm sudo logging is actually retained.
5. **Absolute paths everywhere** — in sudoers rules and inside scripts. Never rely on
   `$PATH` resolution (exploitable via ordering, aliases, or Debian's
   alternatives/symlink layer).
6. **Bind knowledge sources explicitly rather than granting general fetch access:**
   - Static reference material (man pages, doc-base) → lives in the build environment.
   - Living sources (upstream git, Salsa, BTS) → scoped live access to *named*
     repos/packages. Not a general crawl, and not a frozen snapshot — staleness would
     defeat the purpose.
7. **Sandbox at the cheapest tier that's actually sufficient:** dedicated scoped-home
   user → bubblewrap/firejail/systemd-nspawn → full VM via libvirt. Freedom *inside*
   the sandbox can be generous; freedom *at the system boundary* stays minimal no
   matter how trusted the workflow inside is.
8. **Track provenance, not just correctness.** Where a service file, patch, or config
   choice came from (Kali's own tree / Devuan / Gentoo / Artix / newly written) must be
   queryable later via apt-tag, not just left in a comment.

## How these rules apply to work in this repo

- **MCP server design:** every server takes an explicit allowlist of repos/packages it
  may reach. No tool gets a generic "fetch URL" capability. BTS access wraps existing
  tooling (`debbugs` / `querybts` / BTS SOAP), never a bespoke scraper.
- **Nothing executable ships unreviewed.** Scaffolding, config, and docs land by PR;
  anything that would run with elevated rights or unattended additionally needs
  explicit human vetting before first execution (rule 3).
- **When something is genuinely unresolved, ask Jay rather than assume.** Open
  questions are tracked below; don't silently pick an answer to one.

## Conventions

- Develop on the designated feature branch; never push to a different branch without
  explicit permission. Open PRs for review — do not merge them.
- Keep package-facing scripts and configs to absolute paths (rule 5) even in examples
  and tests, so nothing exploitable gets copy-pasted into production later.
- Record where borrowed material came from at the moment it's borrowed (rule 8).

## Open questions (ask, don't assume)

- OpenRC metapackage pinning strategy: apt preferences, equivs dummy packages, or
  both. Current leaning: a config package dropping a priority/held status (possibly
  via diversion), with openrc depending on it so systemd is deprioritized before
  openrc's preinstall runs — but this is not decided.
- Exact scope of BigQuery's systemd-dependency analysis and how its classification
  taxonomy (build exposure → PID-1 dependency) feeds tooling here.
- Cinnamon project: no concrete package/config work defined yet.
