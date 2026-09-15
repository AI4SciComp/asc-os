# Quickstart

First [install the command](installation.md). Then run these commands from
any directory where you want to create a study:

```console
asc-os init ./my-study --dry-run
asc-os init ./my-study
cd ./my-study
asc-os validate --json
asc-os context build CTX-ROOT --harness common --dry-run --json
```

Use `--adopt` only for an existing nonempty repository. It preserves every
existing file and creates only missing research-layer paths. Review dry-run
plans before applying writes.

For a complete synthetic example, run `make examples` from the ASC OS checkout.
