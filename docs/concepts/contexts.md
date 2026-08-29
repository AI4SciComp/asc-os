# Contexts

A context is a bounded research question with explicit inputs, outputs,
acceptance criteria, exclusions, and optional tool/path policy. Parent and input
context references form an acyclic dependency graph. Contexts are not chat
sessions; their authored manifests remain stable project state.

Use `asc-os context list`, `context show`, and `context build`. Building emits a
common content model plus an optional Codex or Claude presentation adapter.
