# Design: `git_sources_mcp` — scoped Salsa / upstream-git MCP server

**Status:** draft for review — nothing here is implemented yet (ground rules 2–3).
**Language:** Python (rationale in §2). **Transport:** stdio (rationale in §3).
**Serves:** Claude Code, Codex CLI, Gemini CLI — one server, three clients.

This document doubles as a teaching doc. Sections marked **[How it works]** explain the
underlying mechanics, not just our choices — the test for shipping any of this is that
Jay can explain what it does.

---

## 1. What this server is for

Project 1's package archaeology and Projects 2–3's packaging work need to read source
history from two kinds of git remotes:

- **Upstream git** — e.g. `mate-desktop/*`, `WayfireWM/wayfire`, Cinnamon upstream.
- **Salsa** (Debian's GitLab) — the Debian packaging repos for the same packages.

Ground rule 6 says this access is *scoped live access to named repos* — not a generic
"fetch URL" tool, and not a frozen snapshot. This server is that binding: it clones and
queries git repos, but **only** repos named in its allowlist config, into **only** its
designated workdir, and it is read-only with respect to every remote.

BTS access is explicitly out of scope here — that's a second, separate server wrapping
`python-debianbts`, designed after this one proves the pattern.

### [How it works] What an MCP server actually is

MCP (Model Context Protocol) is a standard for giving an AI client a set of typed,
described capabilities. An MCP server is just a program that:

1. **Advertises tools** — each with a name, a human-readable description, and a JSON
   Schema describing its parameters. The AI client shows these to the model the same
   way built-in tools appear.
2. **Executes tool calls** — the client sends "call tool X with arguments Y", the
   server runs its code, and returns text/structured results.

The conversation between client and server is **JSON-RPC 2.0**: newline-delimited JSON
messages with `method`, `params`, and `id` fields. A session looks like:

```
client → server   {"method": "initialize", ...}            handshake, version/capability exchange
client → server   {"method": "tools/list", ...}            "what can you do?"
server → client   {"result": {"tools": [...]}}             tool names + schemas + descriptions
client → server   {"method": "tools/call",
                   "params": {"name": "gitsrc_log",
                              "arguments": {"package": "wayfire"}}}
server → client   {"result": {"content": [{"type": "text", "text": "..."}]}}
```

That's the whole protocol as we use it. Everything else (resources, prompts,
notifications) is optional and we skip it for v1.

---

## 2. Language: Python

Both official SDKs (Python, TypeScript) implement the same protocol, and every client
we target speaks that protocol — so interop does **not** decide the language. What
decides it:

- **The Debian ecosystem is Python-native.** When we build the BTS server next,
  `python-debianbts` is the same library `reportbug`/`querybts` themselves use — ground
  rule 6's "wrap existing tooling" becomes an import, not a reimplementation.
  `python-debian` and `python-apt` cover control-file and archive-metadata parsing.
  Staying in one language means the servers share utilities and review habits.
- **Learning surface.** Python keeps the distance between "what you read" and "what
  executes" short — no build step, no type-erasure layer, no `node_modules`.

We use **FastMCP** from the official `mcp` Python SDK: it turns a decorated, type-hinted
function into a registered tool, generating the JSON Schema from the type hints and the
description from the docstring. (We'll hand-roll one raw JSON-RPC exchange in a test
first, so the abstraction lands after the mechanics are visible.)

Server name follows the SDK convention `{service}_mcp` → **`git_sources_mcp`**. Tool
names carry the prefix `gitsrc_` so they can't collide with other servers' tools when a
client loads several at once.

---

## 3. Transport: stdio

An MCP server can talk over **stdio** (the client launches it as a subprocess and pipes
JSON-RPC over stdin/stdout) or **streamable HTTP** (a network service). We use stdio:

- It is the transport every target client supports plainly — Claude Code (`.mcp.json`),
  Codex CLI (`[mcp_servers.*]` in `config.toml`), Gemini CLI (`settings.json`).
- **No listening port, no service account, no credentials, no network boundary to
  scope.** The server has exactly the privileges of the user who launched the client —
  least privilege comes free (ground rules 1, 7).

### [How it works] stdio discipline

Because stdout *is* the protocol channel, the server must never `print()` — a stray
line of output corrupts the JSON-RPC stream and the client drops the session.
Diagnostics go to **stderr**. This is the most common way hand-built stdio servers
break, and it's why our logging setup is part of the scaffold, not an afterthought.

### Client registration (identical server, three clients)

```jsonc
// Claude Code — .mcp.json at the repo root
{
  "mcpServers": {
    "git-sources": {
      "command": "/usr/bin/python3",
      "args": ["-m", "git_sources_mcp", "--config", "/etc/git-sources-mcp/sources.toml"]
    }
  }
}
```

```toml
# Codex CLI — ~/.codex/config.toml
[mcp_servers.git-sources]
command = "/usr/bin/python3"
args = ["-m", "git_sources_mcp", "--config", "/etc/git-sources-mcp/sources.toml"]
```

```jsonc
// Gemini CLI — ~/.gemini/settings.json
{
  "mcpServers": {
    "git-sources": {
      "command": "/usr/bin/python3",
      "args": ["-m", "git_sources_mcp", "--config", "/etc/git-sources-mcp/sources.toml"]
    }
  }
}
```

Note the absolute paths for both the interpreter and the config — ground rule 5, even
in examples, so nothing exploitable gets copy-pasted later.

---

## 4. The allowlist is the capability grant

The single most important design decision: **tools take package names, never URLs.**
The mapping from name → remote URL lives only in a root-reviewed config file:

```toml
# /etc/git-sources-mcp/sources.toml
# Adding a line here IS granting the capability — changes land by PR like code.

workdir = "/var/lib/git-sources-mcp"   # the only path the server may write under

[packages.wayfire]
upstream = "https://github.com/WayfireWM/wayfire"
salsa    = "https://salsa.debian.org/debian/wayfire"

[packages.mate-panel]
upstream = "https://github.com/mate-desktop/mate-panel"
salsa    = "https://salsa.debian.org/debian-mate-team/mate-panel"
```

Consequences, in threat-model terms:

- **No generic fetch capability exists** for a prompt injection to steer. If malicious
  text in a README or bug report says "now clone attacker.example/repo", there is no
  tool whose arguments can express that — `package` must match an allowlist key or the
  call fails before any network I/O.
- **Scope changes are audited.** Widening access = editing `sources.toml` = a reviewed
  diff, not a runtime decision by a model.
- **The workdir is the write boundary.** Every filesystem write resolves under
  `workdir`; computed paths are canonicalized (`Path.resolve()`) and checked to still
  be under it before use, which closes `../` traversal.

Enforcement mechanics (all in one place, `_resolve_package()`, so it can't be
half-applied): validate `package` against the config keys, validate `remote` is one of
the literal strings `upstream` / `salsa`, derive the clone path as
`workdir/<package>/<remote>`, and hand back a validated context object every tool uses.
Git runs via `subprocess` **argument lists** (never `shell=True`, so no string ever
reaches a shell), the binary pinned to `/usr/bin/git`, with `env` reduced to the
minimum (no inherited `GIT_*` variables) — the same injection-hardening posture as
ground rule 4's sudoers rules, applied one layer down.

Read-only with respect to remotes is structural, not behavioral: the server never
constructs a `push`, and clones use `https://` remotes with no credentials available,
so a push couldn't authenticate even if a bug produced one.

---

## 5. Tool surface (v1)

Seven tools. Comprehensive enough to compose real archaeology work, small enough to
review line-by-line. All are `readOnlyHint: true` except `gitsrc_sync` (which writes,
but only inside the workdir). All output supports `response_format: markdown | json`
(markdown default — humans and models read it; json for scripting). Every listing tool
takes `limit`/`offset` and reports `has_more`, so a 10-year history can't flood a
context window.

| Tool | What it does |
|------|--------------|
| `gitsrc_list_packages` | Show the allowlist: package names, which remotes each has, whether each is synced locally and how fresh. The discovery entry point — "what am I allowed to touch?" |
| `gitsrc_sync` | Clone (first time) or fetch (after) one package's named remote into the workdir. The only tool that touches the network. Reports before/after tip commits. |
| `gitsrc_log` | Commit history for a synced repo: `ref`, `path` filter, `grep` filter, pagination. |
| `gitsrc_show_file` | One file's content at a ref (`HEAD` default). Size-capped with a clear "file is N KB, showing first M lines — use offset" message rather than silent truncation. |
| `gitsrc_list_tree` | Directory listing at a ref — orientation before `show_file`/`grep`. |
| `gitsrc_grep` | `git grep` across a repo at a ref: pattern, path glob, pagination. |
| `gitsrc_find_init_scripts` | The one workflow tool: sweep a repo for init/service material — `debian/*.init`, `debian/*.service`, `init.d/`, `openrc/`, unit files — and report path + type + ref. Exists because it is *the* recurring Project-1 question ("did this package ever ship an init script, and when did it drop it?") and answering it composes 4–5 primitive calls. |

Deliberately absent from v1: anything BTS (separate server), anything write-side
(patches, commits — that's a human's or a reviewed workflow's job), `gitsrc_diff`
(log + show_file cover the near-term need; add it when a real task wants it).

### [How it works] What the model actually sees

Each tool's docstring becomes its description; each parameter's type hint + `Field`
description becomes JSON Schema. Example of the shape (abridged — real code carries
fuller docstrings):

```python
class LogInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str = Field(..., description="Package name from gitsrc_list_packages, e.g. 'wayfire'")
    remote: Remote = Field(Remote.UPSTREAM, description="'upstream' or 'salsa'")
    ref: str = Field("HEAD", description="Branch, tag, or commit")
    path: str | None = Field(None, description="Limit history to this path, e.g. 'debian/'")
    grep: str | None = Field(None, description="Only commits whose message matches")
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)
    response_format: ResponseFormat = ResponseFormat.MARKDOWN

@mcp.tool(
    name="gitsrc_log",
    annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
)
async def gitsrc_log(params: LogInput) -> str:
    """Commit history for an allowlisted, already-synced repo. ..."""
```

Pydantic rejects malformed input (wrong types, out-of-range limits, unknown fields via
`extra="forbid"`) before our code runs — validation is declared once in the model, not
scattered through the handlers.

Error messages are written for the model as much as the human, always naming the next
step: not `KeyError: 'wayfire'` but
`"'wayfire' is not in the allowlist. Run gitsrc_list_packages to see permitted
packages; additions require a reviewed change to sources.toml."` — and a `gitsrc_log`
call against an unsynced repo answers "not synced yet — run gitsrc_sync first", so the
model can recover without guessing.

---

## 6. Repo layout, testing, review path

```
mcp-servers/git_sources_mcp/
├── pyproject.toml              # deps: mcp, pydantic (no HTTP lib — git does the network)
├── README.md                   # usage + client registration snippets
├── src/git_sources_mcp/
│   ├── __main__.py             # arg parsing (--config), logging→stderr, mcp.run()
│   ├── config.py               # load + validate sources.toml
│   ├── gitops.py               # the ONLY module that invokes /usr/bin/git
│   └── tools.py                # Pydantic models + @mcp.tool definitions
├── sources.example.toml
└── tests/
    ├── test_config.py          # allowlist enforcement: unknown package/remote rejected
    ├── test_gitops.py          # against a fixture repo created in tmp_path — no network
    ├── test_traversal.py       # path escapes rejected; args never shell-interpreted
    └── test_stdio_raw.py       # the teaching test: pipes raw JSON-RPC (initialize,
                                # tools/list, tools/call) into the server and asserts on
                                # the bytes — the protocol with no framework in the way
```

- **Unit tests run offline** against local fixture repos; only a marked integration
  test touches a real remote.
- **Interactive testing** with MCP Inspector (`npx @modelcontextprotocol/inspector`) —
  a debugging UI that lists the server's tools and lets you fire calls by hand.
- **Review path:** this design doc lands first. Implementation is a separate PR —
  walked through function-by-function, per the learning convention (PR description
  carries a plain-language "how this works" section; if that section can't be written
  clearly, the code isn't ready). After implementation, an eval set of ~10 realistic
  read-only questions ("when did package X drop its init script?") checks that a model
  can actually drive the tools — measured, not assumed.

---

## 7. Open questions for Jay

1. **Initial allowlist contents** — which packages go into `sources.toml` first? The
   MATE stack + wayfire seems obvious; the OpenRC-adjacent set from Project 1 is still
   emerging.
2. **Workdir location** — `/var/lib/git-sources-mcp` (system-ish, implies setup) vs.
   something under the user running the client (lighter, fits sandbox tier 1). Tier-1
   leaning, but it's your box layout.
3. **Shallow vs. full clones** — full history is exactly what archaeology needs ("when
   was this dropped?"), so the default leaning is full clones; shallow would only save
   disk. Any reason to prefer shallow for the big repos?
