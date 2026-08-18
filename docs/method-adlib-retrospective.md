# Retrospective: the ad-lib method, and the shape of its failures

**What this is:** evidence for `design-bcck-architecture.md` §1.1, which claims that
a contained AI still produces plausible wrong output and that human review capacity
is the binding constraint. That claim should not sit in the design unsupported. The
support is the session that produced the design.

**Scope and honesty about it:** one session, one operator, no control condition,
recorded by the participant who made the errors. This is a case note, not a study.
Treat the *shape* as the finding; treat the counts as anecdote.

---

## The method

Design by conversation. No upfront specification: an idea is raised, sharpened
across turns, and committed once it stabilises. The AI drafts continuously; the
human redirects. Nothing is planned more than roughly one artifact ahead.

**What it produced here:** repo scaffolding, a working MCP server (~1,500 lines
with tests), a design note for it, a knowledge schema, and the BCCK architecture —
across a single sitting, four merged PRs and one open.

**What it cost:** the failures below, all of which reached a commit or a push
before a human caught them.

---

## Failure log

| # | Failure | Class | Caught by | Cost |
|---|---|---|---|---|
| 1 | Pushed commits onto a branch whose PR was already merged; no new PR opened | lost process state across a boundary | human, after the fact | user had to open and squash-merge a cleanup PR |
| 2 | Repeated #1 after the next merge, having explicitly said it was fixed | same, recurrence | human | branch reset + force-push |
| 3 | No `LICENSE` or `.gitignore` until prompted | omitted standard scaffolding | human, unprompted by any tool | would have committed `__pycache__` into the first Python diff |
| 4 | Wrote five sections of containment architecture without stating what was being contained | missing premise | human ("the ai represents a bigger problem") | threat model absent from the design until late |
| 5 | Named single layers "load-bearing" inside an explicitly defense-in-depth design | internal contradiction | human ("defense in depth") | two sections framed wrong |
| 6 | Pursued verification of s6's allocation behaviour while the AI was the larger risk | misallocated attention | human ("you're rabbit holing") | a turn spent on the wrong component |
| 7 | Justified verifiable evidence identifiers primarily as injection resistance; the real reason is review cost | inverted rationale | human, indirectly | design rule stated backwards |

---

## The shape

Five observations, in descending order of how much they should change the design.

1. **None were execution errors.** The code ran, the tests passed, the git
   operations succeeded, the schemas validated. Every failure was a *framing*
   error: a missing premise, a wrong emphasis, an inverted rationale, or lost
   state across a process boundary.

2. **Every one was fully within grants.** Nothing in §3 or §5 of the architecture
   would have detected any of them, because none was a violation. This is the
   concrete instance of §1.1's claim: containment bounds reach, not correctness.

3. **Every one was caught by the human, none by a mechanism.** Not one was caught
   by a test, a linter, a schema, or a hook. The single control that worked, in
   all seven cases, was a person reading the output.

4. **The corrections were extremely cheap and extremely high-leverage.** "Fuck
   License and .gitignore." "You're rabbit holing." "Defense in depth." Three to
   six words each, and each redirected a substantial amount of subsequent work.
   The asymmetry is the useful part: **the human's comparative advantage is
   framing correction delivered at very low token cost; the AI's is volume of
   internally coherent artifact.** A collaboration shaped around that asymmetry
   spends human attention on premises and emphasis, not on line-by-line
   correctness.

5. **Framing errors compound silently.** This is the actual limitation of the
   ad-lib method. Each artifact looks fine in isolation — that is what made #4 and
   #5 survive several turns and multiple commits. Without an upfront spec there is
   no artifact to check the framing *against*, so the only detector is a human who
   notices the premise is missing. Volume makes this worse: more plausible output
   per unit of review attention is precisely the failure mode §1.1 describes, and
   this session is an instance of it.

---

## What follows for the framework

- The recurrence of #1 as #2 is the most damning entry, because it happened after
  an explicit correction. **Process state across boundaries is not reliably held
  by an agent and should be held by a mechanism** — a fact BCCK already asserts
  for grants and audit logs (§3.1), now with evidence that it applies to mundane
  workflow state too.
- #3 argues for scaffolding checks that are deterministic rather than remembered.
- #4, #5 and #7 are all "the document does not state its own premise or has its
  emphasis inverted." No current mechanism catches this class. If one is wanted,
  it is a **review checklist applied to design documents** — does it state what is
  untrusted, does it name any single point as load-bearing, is each rule's stated
  rationale its actual one — not more tests.
- Nothing here argues against the ad-lib method for *generation*. It argues that
  generation and framing-review are different activities, and that the second is
  the scarce one.
