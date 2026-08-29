# ASC OS

ASC OS is the generic, local-first AI research operating system for
AI4SciComp. It models bounded contexts, declared covers, compatibility
overlaps, evidence, decisions, lifecycle runs, deterministic restriction, and
manifest-only gluing. It is not an operating-system kernel, numerical runtime,
LLM provider, proof assistant, or autonomous shell agent.

The v0.1 implementation is Python-only and model-agnostic. Authored YAML under
`research/` remains canonical; generated bundles are reproducible projections.

## Install for development

Python 3.12 through 3.14 is supported.

```console
uv sync --frozen --all-groups --all-extras
uv run asc-os --version
uv run asc-os doctor --json
```

The base distribution has no MCP dependency. Install the optional official
SDK surface with `pip install 'asc-os[mcp]'`; the server remains local stdio
only.

## Quick start

```console
asc-os init ./study --dry-run
asc-os init ./study
cd ./study
asc-os validate
asc-os context build CTX-ROOT --harness codex --dry-run
```

The synthetic [AP kinetic pilot](examples/ap-kinetic-study/RESEARCH.md)
demonstrates all major contracts without asserting scientific novelty.

## Safety boundary

ASC OS never exposes arbitrary shell or Python execution, Git mutation,
credential access, network fetching, or a network-listening MCP transport.
Generated writes are confined, locked, atomic, and ownership checked. Skills
and overlap checks are descriptive data rather than executable code.

See [architecture](docs/architecture/overview.md),
[CLI reference](docs/reference/cli.md), [MCP guide](docs/guides/mcp.md),
[security policy](SECURITY.md), and [contributing guide](CONTRIBUTING.md).

License: Apache-2.0. No release or package publication is performed by this
development branch.
