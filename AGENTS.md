# Repository instructions

These instructions apply to the entire ASC OS repository.

- Treat `docs/architecture/`, `schemas/v1/`, `RESEARCH.md`, and the CLI/MCP
  contracts as coordinated public interfaces.
- Use Python 3.12+, typed public APIs, Google-style docstrings, an 80-column
  target, Ruff, Pylint, and strict Pyright.
- Keep YAML parsing, path confinement, canonical hashing, atomic writes, and
  generated-file ownership checks explicit and directly tested.
- Keep the CLI and MCP adapters thin over the same deterministic service layer.
  MCP is local stdio only and adds no shell, Python, Git mutation, credential,
  network-fetch, or unrestricted path capability.
- Skills and overlap checks are declarative data. Never execute manifest text.
- Say declared cover, declared overlap, validated compatibility, and gluing
  manifest; do not claim formal topos or global-correctness proofs.
- Do not weaken, skip, or hide a failing test. Keep branch coverage at least
  90% and run `make check` before publication.
- Do not commit caches, raw logs, generated build artifacts, credentials, or
  private research content. Do not publish releases or packages from this repo.

