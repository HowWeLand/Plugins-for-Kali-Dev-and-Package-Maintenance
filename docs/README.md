# docs

Design notes, architecture decisions, and provenance conventions (apt-tag usage, sandbox tier choices).

Notes:

- `design-bcck-architecture.md` — **the model everything else is designed against.**
  Behavior / Capability / Connection / Knowledge, the Tarski rule for knowledge
  hierarchy, and the s6 supervision-tree enforcement layer. Living document.
- `design-git-sources-mcp.md` — the scoped git MCP server (implemented). See BCCK §9
  for how it gets re-read under the new model.
- `method-adlib-retrospective.md` — failure log from the session that produced the
  BCCK note, and what the shape of those failures implies. Evidence for BCCK §1.1.
