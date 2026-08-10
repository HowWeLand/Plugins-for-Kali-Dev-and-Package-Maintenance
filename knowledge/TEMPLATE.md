---
package: example-package          # must match filename: knowledge/example-package.md
projects: [openrc]                # openrc | mate-wayfire | cinnamon
status: tracking                  # tracking | active | blocked | done
upstream: https://github.com/example/example-package
salsa: https://salsa.debian.org/debian/example-package
bts: []                           # e.g. [1012345, 1067890]
service_files: []
# service_files entry shape:
#   - path: /etc/init.d/example
#     provenance: devuan          # kali | devuan | gentoo | artix | own
#     source: https://git.devuan.org/...  (or "devuan example-package 1.2-3")
#     adapted: false              # true if modified from source, false if verbatim
updated: 2026-08-10
updated_by: jay                   # jay | claude-code | claude-chat | codex | gemini
---

# example-package

## Findings

- 2026-08-10: (example) upstream dropped `debian/example.init` in commit `abc1234`
  (v2.0 packaging rework); last version shipping it was 1.9-2.

## Decisions

- (example) Use Devuan's init script verbatim — paths and user/group match Debian's.

## Open questions

- (example) Does the OpenRC SysV-compat mode handle this script's `status` verb?
