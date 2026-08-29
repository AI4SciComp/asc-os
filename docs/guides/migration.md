# Adoption and migration

For an existing repository, begin with `asc-os init PATH --adopt --dry-run`.
Review every planned path, then apply with `--adopt`. Existing `AGENTS.md`,
`CLAUDE.md`, research files, source code, and Git state are preserved.

Adoption should start as an optional research sidecar on a feature branch.
Do not make a scientific foundation depend on ASC OS, repurpose active release
work, or copy repository history. Record future integration in a focused issue
when active work prevents safe adoption.
