# Quickstart

```console
uv sync --frozen --all-groups --all-extras
uv run asc-os init /tmp/my-study --dry-run
uv run asc-os init /tmp/my-study
cd /tmp/my-study
asc-os validate --json
asc-os context build CTX-ROOT --harness common --dry-run --json
```

Use `--adopt` only for an existing nonempty repository. It preserves every
existing file and creates only missing research-layer paths. Review dry-run
plans before applying writes.

For a complete synthetic example, run `make examples`.
