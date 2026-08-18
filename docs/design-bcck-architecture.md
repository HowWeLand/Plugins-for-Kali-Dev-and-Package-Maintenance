# Design: BCCK — Behavior, Capability, Connection, Knowledge

**Status:** living design note. Nothing here is implemented. Amend in place as
decisions land; this file is the model everything else in the repo is designed
against.

**Authorship posture:** written by an author who does not execute it. Drafting and
running are deliberately separated — verification is Jay's, with outside-the-tree
review. Consequence for how this is written: no claim rests on "it worked when I
tried it," and anything empirical is listed in §12 rather than asserted.

**Supersedes:** nothing yet, but it re-frames `design-git-sources-mcp.md` — see §9.

---

## 1. Why

A skill today is three unrelated things fused into one prose blob: a set of verbs,
a partial set of resources those verbs may touch, and a policy about when to use
them. Agents build on skills, so they inherit the fusion and add more. Every one
of those loaded into context costs tokens on all three axes even when only the
verbs were needed, and none of the three can be reasoned about independently —
you cannot ask "what may this reach?" without reading a page of instructions.

BCCK splits them into four concerns that can be declared, composed, and enforced
separately.

---

## 2. The four concepts

| Concept | Access-control reading | Form |
|---|---|---|
| **Capability** | the verb set — what actions exist at all | MCP servers / tools |
| **Connection** | the object set — which resources those verbs may address, where output lands, where knowledge is read and written | named bindings |
| **Knowledge** | the state — durable, versioned, provenanced facts | corpora + bus |
| **Behavior** | the policy — what *should* happen, attached to a principal | agent prose |

### 2.1 Behavior is the only non-composable part

Capability, Connection, and Knowledge are data: generatable, parameterizable,
diffable, machine-checkable. Behavior is irreducible hand-written prose.

Two consequences, both load-bearing:

1. **Length in an agent's behavior section is a design smell.** If it is long,
   capability or knowledge has leaked into it. This is lintable: an agent file
   should read as a grant manifest plus a few lines of "you are the thing that
   does X."
2. **Behavior is therefore the right home for authorization identity.** The
   principal is precisely the thing that cannot be derived from parts.

### 2.2 Agents

An agent is a **principal**: a role name, a grant set (capabilities × connections
× knowledge access), and a short behavior. It is not a bundle of skills; it is the
thing a grant attaches to.

Critically, an agent definition is **not self-enforcing**. A model reading its own
agent file and declining to exceed its grant is advisory, and prompt injection
routes around advisory boundaries by definition. The definition must compile down
to something outside the model: which servers get launched, with which connection
bindings, as which uid, in which namespace, with which mounts. §5 is that
compilation target.

---

## 3. The Tarski rule

> **An agent may not write to its own truth predicate.**

An agent may write to the bus (§8) and to the project (work product, reviewed).
It may never write the corpus it reads as ground truth.

What this protects is not consistency in the logical sense — it is **provenance
distinguishability**. If an agent can write to the corpus it treats as true, then
"I read this in the Debian wiki" and "I asserted this last Tuesday" become the
same kind of object, and no later reader can tell them apart. The truth predicate
must be written one level up, or the distinction dies.

### 3.1 Three artifacts live at level N+1

The rule generalizes past knowledge. An agent may not write:

- its own **knowledge** — else it forges facts;
- its own **audit log** — else it forges history;
- its own **grants** — else it forges authority.

Three concerns that would otherwise need three separate policies collapse into one
structural rule: all three are artifacts of the level above. If the level above
holds them, none are forgeable from inside.

### 3.2 Promotion, not self-certification

Discovery and canonization are separate operations held by separate roles:

```
agent discovers  →  posts a CLAIM (bus, untrusted, carries evidence)
                 →  reviewed at level N+1
                 →  promoted to KNOWLEDGE (corpus, trusted at level N)
```

Same instinct as "open a PR, don't merge," applied to facts instead of code
(ground rule 2).

### 3.3 Enforced by the kernel, not by prose

The knowledge corpus is a **read-only bind mount** inside the agent's namespace.
An agent attempting to violate the hierarchy receives `EROFS`, not a stern
paragraph in its prompt. This is the whole point of §5: the hierarchy is a mount
table, not an instruction.

### 3.4 The hierarchy terminates at the human

Level N+1 may not write its own knowledge either; it is written by N+2. At the
top is Jay. The human is the only self-referential writer, which is correct rather
than a gap — that is where authority originates.

---

## 4. Connections

A connection is a **named** binding, declared once and referenced by grants. Not a
URL an agent can supply; a name an agent can be given. Kinds:

- **source** — where knowledge may be pulled from (a named repo, a named wiki
  mirror, a named BTS package scope).
- **workspace** — where an agent may operate and write work product.
- **knowledge-read** — which corpora/slices are mounted readable.
- **knowledge-write** — which bus streams may be posted to. Distinct from
  knowledge-read by §3, and much more rarely granted.

Because connections are named and held by the tree (§5), two agents needing
different scopes are two trees — the namespace *is* the grant.

---

## 5. Runtime: the supervision tree

The compilation target for §2.2. s6, because supervision trees nest arbitrarily,
do not require PID 1, and compose with namespaces and cgroups.

### 5.1 Topology

```
level 0   root s6-svscan                     system supervision
level 1   privileged tree root               creates namespace + cgroup, drops privilege
level 2   unprivileged s6-svscan (in ns)     spawns invocations, logs, reaps
          └── invocation, invocation, ...    ephemeral agent processes
```

Level 1 is the boundary: it scopes namespaces and cgroups, then chain-loads
(`s6-applyuidgid` / `s6-setuidgid`) into level 2. Level 2 does all the work of
running agents. Level 0 exists only to supervise level 1 and catch anything that
double-forks its way out.

### 5.2 Namespace per tree, cgroup per invocation

**The namespace is the grant.** Agents within one tree share connections precisely
because they share the boundary — isolating them from each other would be paying
setup cost to separate things that are meant to be identical. Namespace + mount
setup is not free; invocation churn is the hot path; amortize it per tree.

**The cgroup is the kill boundary.** Level 2 creates a cgroup v2 subgroup per
invocation under the tree's cgroup. Far cheaper than a namespace, gives per-agent
accounting and limits, and gives `cgroup.kill`: write `1`, every process in it
dies atomically — no signal races, no walking a process tree, no window in which
something forks while the kill is in flight.

This is also what closes the double-fork hole properly. A double-forked orphan
escapes its *parent*, which is why level 0 reparents; it cannot escape its
*cgroup*, because membership is inherited and unchangeable without privilege.
`cgroup.kill` is the primary reap; level-0 reparenting is the backstop.

### 5.3 Reaping

If level 2 is PID 1 of the tree's PID namespace, orphans reparent to it
automatically. If the PID namespace is deliberately skipped, `PR_SET_CHILD_SUBREAPER`
on level 2 gives the same reparenting without one. **Decide explicitly** — it
determines whether sibling invocations can see each other's PIDs, which matters
when composing parallel invocations in one tree.

### 5.4 Layer boundary: s6-rc vs. instanced services

`s6-rc` is a state machine over a **compiled, static** database. Correct for the
tree skeleton (bring up "the codex tree" with dependencies; tear down in reverse
topological order). Wrong for invocation churn — recompiling a database on every
agent turnover is absurd.

- **s6-rc manages trees.**
- **s6 instanced services manage invocations** (`s6-instance-create` / `-delete`,
  dynamic, no recompilation). Verify the instance tooling against the s6 version
  Kali ships.

Getting this boundary wrong is the most likely way this design ends up taking
hundreds of milliseconds to start an agent.

### 5.5 Logging

A **catch-all logger at the tree level**, not a logger per invocation — one
append-only stream per tree, no logger churn as agents cycle.

The enforcement is stronger than "the level above writes it." The idiom is a
**pipe**: the supervised process receives a *write end* as fd 1, and `s6-log` — a
separate process, separately privileged — owns the log files. The agent never
holds a path to its own log, so it cannot address the storage behind the pipe at
all. This is Tarski (§3.1) enforced by **fd topology**, which is a harder boundary
than the read-only mount of §3.3: a mount can at least be named by the process it
constrains. Rotation lives in `s6-log` too, so an agent cannot fill the disk by
logging.

### 5.6 Why s6 specifically

Four properties, in descending order of how load-bearing they are:

1. **Small TCB.** The supervision layer is the trusted computing base for the
   entire authorization argument in §2.2 and §3. Given the review posture — manual
   review plus outside-the-tree help, nothing executed by its author — a TCB a
   human can read end to end is what makes that review meaningful rather than
   ceremonial. This is a difference in kind, not degree, from auditing systemd's
   PID 1.
2. **Chain loading leaves no privileged parent.** Because execline chain-loads —
   each step `exec`s the next rather than forking — namespace entry, uid drop, and
   cgroup move consume the privileged process rather than spawning from it. No
   privileged parent survives holding a handle to the constrained child, which is
   the residue a fork-based setup leaves behind.
3. **Allocation discipline in the supervision loop.** The steady-state loop does
   not allocate, so a supervisor cannot die under memory pressure — the failure
   that would otherwise take the supervision guarantee with it. Corollary for
   §5.2: a fixed, known supervision footprint means the tree's `memory.max` can be
   set tightly and any overage attributed to the agent rather than to overhead.
4. **Independent, separately privileged logging.** See §5.5.

**Provenance of 3 and 4:** both are properties **claimed by s6's author**, not
measured here. Upstream's account of its own design intent is good evidence of
what the software is *trying* to guarantee, and skarnet's track record makes it
credible — but an author's claim is not verification, and these two carry weight
in the security argument, so they stay in §12 until someone checks them locally
(rule 8: record where a claim came from at the moment it is borrowed).

**The cost, stated honestly:** s6 does less. There is no declarative sandboxing
vocabulary comparable to systemd's `Protect*` / `Restrict*` / `SystemCallFilter`
directives — every such constraint is composed by hand through chain loading, so
what systemd gives as a reviewed default becomes something this framework must get
right itself. Ergonomics are spartan, and execline is unpleasant until it clicks.
For a hand-reviewed framework this is an acceptable trade; it is still a trade.

---

## 6. Invocation lifecycle

Agent identity is a fiction worth discarding. Each invocation is a fresh forward
pass; continuity is reconstructed from context either way, so killing and
respawning costs nothing that was real. Continuity that matters is *human*
auditability, and forcing handoff through a written record delivers that better
than in-process memory: nothing carries over invisibly, so ground rule 8 falls out
of the architecture instead of being bolted on.

```
spawn (role template)  →  read bus + knowledge  →  work  →  post findings  →  cgroup.kill
                                                                                    ↓
                                            successor spawns fresh, reads what was posted
```

### 6.1 Who signs the spawn request

**The reap boundary is where authority is assigned and no human is watching, so it
is the boundary injection will target.**

Therefore: a spawn request names a **pre-registered role**, never a grant set. The
supervisor holds role→grants. Roles are human-vetted artifacts — ground rule 3's
"fixed and vetted beforehand," applied to authority instead of scripts. A request
may say `instantiate archaeologist`; it may never say `instantiate something that
can write to the package tree`.

Corollary: a dying agent may not influence its successor's grants, directly or by
writing a suggestion somewhere that something else acts on. Delegation, where it
exists at all, attenuates — never widens.

### 6.2 The cost curve

Every reap makes the successor pay full re-orientation. Too little in the handoff
and findings get re-derived three times; too much and the bus has reinvented an
ever-growing context by another name. This tension — not injection — is the real
design constraint on the message format (§8).

---

## 7. Knowledge substrate

Two kinds of knowledge with different trust, lifecycle, and writers, therefore
different storage:

| | Reference corpora | Bus |
|---|---|---|
| Content | Kali wiki mirror, Kali packaging/forks, Debian wiki + internals, MATE dev, wlroots, mate-wayland variants and plugins | inter-invocation posts |
| Written by | sync/render jobs, human review | agents |
| Volume | high | low |
| Trust on read | trusted at level N | **always untrusted** |
| Substrate | git-tracked markdown + front matter | maildir-style dir |

**Files are the source of truth; any index is a generated artifact.** SQLite +
FTS5 (embeddings if they earn their place) is a derived index, rebuildable from
the files. Do not invert this, or the remix layer (§8.3) becomes the thing that
cannot be reviewed. This is the decision already recorded in `knowledge/README.md`,
now load-bearing.

For the bus specifically, git is the wrong substrate: high write frequency, no
per-post review, append-only. A **maildir-style directory** — write to `tmp`,
atomic `rename()` into `new` — gives multiple concurrent writers with no locking
and bind-mounts cleanly into a namespace.

### 7.1 Rendering and licence

Reference corpora need a render pipeline into an AI-ingestible form. Every
rendered unit carries `source`, `fetched`, and **`licence`** — Debian wiki, Kali
docs, and upstream READMEs differ, and remixing strips context. Licence is the
context most regretted later, especially for anything volunteered upstream.

---

## 8. Bus protocol

Inspired by the agent-social-network idea, stripped of the anthropomorphic
theatre: it is message passing between invocations, chunked and processed to
**lower, not eliminate**, prompt injection.

### 8.1 The bus expresses findings, never authority

**No imperative field exists.** If a post cannot say "do X," injection through the
bus has nothing to grab, and the reap boundary (§6.1) stays safe. This is the
single highest-value constraint in the protocol.

### 8.2 Post shape

Typed records, not prose — free text is where injection hides:

- `claim` — what was found.
- `evidence` — **verifiable identifiers only**: 40-hex commit, BTS number, path
  at a ref. Verifiable means checkable against the reference corpora rather than
  believed.
- `tags` — for retrieval and remix.
- `open_question` — explicitly not an instruction.
- `provenance` — invocation id, role, **and the grants that role held**. A post
  from a read-only archaeology role that reads like an instruction is
  structurally suspicious, and that is machine-detectable.

On read, posts are served as data inside an explicit untrusted-content envelope,
never spliced into instruction position.

### 8.3 Bounded reads, and remix

Nobody reads the feed; everyone reads a tagged, filtered, paginated query result.
Context economy and blast radius are the same lever.

The payoff of small, individually addressable, well-tagged units with provenance:
a query assembles a **bespoke context per task** instead of loading whole
documents. That is the real improvement over dumping a wiki into a vector store,
and it composes with BCCK exactly — knowledge units are the atoms, Connections
define which slices an agent may address, and the query is the remix.

---

## 9. Re-reading `git_sources_mcp`

The existing server (merged, PR #4) makes exactly the mistake BCCK predicts: the
`sources.toml` allowlist is a **Connection** welded into the **Capability** as
startup config.

Consequences: scope is fixed per server *process*, so two agents needing different
repo scopes require two server instances; and the grant is invisible to any
authorization layer that might reason about it.

**Refactor direction** (not yet scheduled): the server exposes git verbs; the
allowlist becomes a named connection; the agent's grant says which connections it
receives. The server stops owning scope and starts receiving it.

This does not invalidate the merged work — the enforcement inside `gitops.py`
(pinned binary, argument lists, workdir containment, option-injection guards)
is orthogonal and stays.

---

## 10. What BCCK is not

Claude Code, Codex CLI, and Gemini CLI each have fixed runtime primitives. BCCK is
a **source model**: the four object types are authored here, and each client's
artifacts (skills, agent files, `.mcp.json` / `config.toml` / `settings.json`
entries) are **generated** from them. It is not a new engine and does not require
those clients to change.

The supervision tree (§5) is the enforcement layer *under* whichever client runs,
not a replacement for it.

---

## 11. Open questions

1. **PID namespace or subreaper** (§5.3) — decides sibling PID visibility within a
   tree.
2. **Promotion mechanics** (§3.2) — is promotion a human-only operation, or may a
   dedicated higher-level role promote claims whose evidence it re-verified
   mechanically?
3. **Bus retention** — do posts expire, compact, or persist forever? Interacts
   with §6.2's cost curve and with the audit story.
4. **Generation vs. hand-authoring** (§10) — which client artifacts are generated
   first, and does the generator live in this repo or in the plugin?
5. **s6 version** — confirm instanced-service tooling in the s6 Kali ships, and
   confirm OpenRC's `supervisor="s6"` backend for the Project 1 tie-in.

---

## 12. Claims to verify

Everything in this repo is written by an author who does not execute it: drafting
and running are separated on purpose, and verification belongs to Jay and to
outside-the-tree review. Nothing below has been observed — each is a claim that a
reviewer should confirm before the design leans on it.

| # | Claim | Where it matters | How to check |
|---|---|---|---|
| 1 | s6's steady-state supervision loop performs no dynamic allocation *(upstream claim — skarnet)* | §5.6.3 — justifies tight `memory.max` and "supervisor cannot OOM" | read `s6-supervise` / skalibs source; observe RSS over a churn cycle |
| 2 | `cgroup.kill` reliably kills double-forked descendants | §5.2 — the primary reap; the whole "poof" story | spawn a double-forking child, write `1`, confirm nothing survives |
| 3 | Instanced services (`s6-instance-create` / `-delete`) exist and are dynamic in the shipped s6 version | §5.4 — invocation churn without recompiling an s6-rc database | `s6-instance-create --help`; check the package version |
| 4 | Namespace teardown is complete when the last process exits | §5.2 — the "no pollution" guarantee | check `/proc/*/ns/*` refcounts before and after a tree dies |
| 5 | A read-only bind mount cannot be remounted rw from inside a user namespace by an unprivileged agent | §3.3 — Tarski's enforcement | attempt `mount -o remount,rw` as the agent uid inside the tree |
| 6 | An agent holding only a pipe write-end cannot reach `s6-log`'s files *(upstream claim — skarnet)* | §5.5 — the stronger Tarski boundary | inspect the agent's `/proc/self/fd`; attempt to open the log path |
| 7 | OpenRC supports `supervisor="s6"` as documented | Project 1 tie-in | OpenRC docs and source for the shipped version |

Claim 5 is the one to check first. It is the single point on which the Tarski rule
rests, and it is the one most sensitive to kernel version and user-namespace
configuration — if it does not hold as stated, §3.3 needs a different mechanism
rather than a caveat.
