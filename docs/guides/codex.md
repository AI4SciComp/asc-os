# Codex guide

Build a bounded Codex adapter with:

```console
asc-os context build CTX-ORBIT --harness codex --dry-run
```

The compiler emits a prompt and `AGENTS.fragment.md`; it never replaces a root
`AGENTS.md`. `--install-entrypoint` creates a concise root entrypoint only when
none exists. Use the fragment with the repository's authored instructions and
validate before handoff.
