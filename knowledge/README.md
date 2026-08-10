# knowledge/ — shared findings, one file per source package

The shared store for what the collaborators (Claude Code, Codex CLI, Gemini, Jay)
surface while working: package archaeology results, BTS state worth remembering,
service-file provenance, decisions. Git-tracked markdown instead of a database, on
purpose:

- Every collaborator already reads/writes files and git — no service, no credentials,
  no second container to scope (ground rules 1, 7).
- Findings land by PR, so knowledge is reviewable and reversible like code (rule 2).
- Provenance is native: front matter says who/where/when, git history backs it (rule 8).

If querying ever outgrows `grep`, the MCP layer grows query tools *over these files*;
any index (e.g. SQLite) would be a generated artifact, never the source of truth.

## Format

One file per Debian **source package**: `knowledge/<source-package>.md` (e.g.
`knowledge/wayfire.md`). Copy `TEMPLATE.md` to start one.

Each file = YAML front matter (the machine-parseable facts) + terse markdown body (the
prose findings). Tools parse the front matter; humans read the bullets.

### Front matter fields

| Field | Meaning |
|-------|---------|
| `package` | Debian source package name — must match the filename |
| `projects` | Which of the effort's projects this touches: `openrc`, `mate-wayfire`, `cinnamon` |
| `status` | `tracking` (watching, no work yet) · `active` (being worked) · `blocked` (see body for why) · `done` |
| `upstream` | Upstream git URL, or `null` if none/unknown |
| `salsa` | Salsa repo URL, or `null` |
| `bts` | List of BTS bug numbers we care about (numbers only — tooling derives the URL) |
| `service_files` | List of entries: `path` (absolute, rule 5), `provenance` (one of `kali` / `devuan` / `gentoo` / `artix` / `own`), `source` (URL or package+version it was taken from), `adapted` (`true` if modified from source, `false` if verbatim) |
| `updated` | Date of last substantive edit (YYYY-MM-DD) |
| `updated_by` | Who edited: `jay` / `claude-code` / `claude-chat` / `codex` / `gemini` |

`service_files.provenance` uses the same vocabulary as the apt-tag provenance scheme
(rule 8) so the two stay joinable. Record provenance **at the moment material is
borrowed**, not retroactively.

### Body sections

Keep all three, keep them terse — bullets, not essays:

- **Findings** — facts surfaced, each with where it came from (commit, bug number,
  file path). Date-prefix each bullet.
- **Decisions** — choices made for this package and the one-line why.
- **Open questions** — unresolved items. Ask Jay; don't silently resolve one (repo
  rule). Remove when answered, moving the answer into Findings or Decisions.

## Conventions

- Terse wins. A bullet a human can scan beats a paragraph nobody reads.
- Never delete a Finding because it became irrelevant — mark it superseded with a
  dated note. History is the point.
- BTS numbers, commit hashes, and file paths are the currency here — always include
  them so a claim can be re-verified.
- Files land by PR like everything else.
