# Contributing

Read `AGENTS.md`, `RESEARCH.md`, the architecture decisions, and the nearest
repository instructions before editing. Discuss schema-breaking changes before
implementation; stable v1 breakage requires a new API version.

Use Python 3.12+, typed public APIs, Google-style docstrings, Ruff, Pylint, and
strict Pyright. Every security boundary and manifest kind needs a direct test.

```console
uv sync --frozen --all-groups --all-extras
make check
```

Submit focused changes from a feature branch. Never add credentials, private
research data, generated caches, arbitrary-execution features, or unrelated
domain logic. Pull requests remain unmerged until an authorized maintainer has
reviewed the validation evidence.
