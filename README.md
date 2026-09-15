# ASC OS

ASC OS is the generic, local-first AI research operating system for
AI4SciComp. It models bounded contexts, declared covers, compatibility
overlaps, evidence, decisions, lifecycle runs, deterministic restriction, and
manifest-only gluing. It is not an operating-system kernel, numerical runtime,
LLM provider, proof assistant, or autonomous shell agent.

The v0.1 implementation is Python-only and model-agnostic. Authored YAML under
`research/` remains canonical; generated bundles are reproducible projections.

## Install the command

Python 3.12 through 3.14 and [uv](https://docs.astral.sh/uv/) are supported.
Install the wheel from the
[v0.1.0 GitHub release](https://github.com/AI4SciComp/asc-os/releases/tag/v0.1.0)
once into an isolated user tool environment:

```console
uv tool install --python 3.12 https://github.com/AI4SciComp/asc-os/releases/download/v0.1.0/asc_os-0.1.0-py3-none-any.whl
asc-os --version
asc-os doctor --json
```

You can then run `asc-os` from any directory without activating a virtual
environment. If the command is missing from PATH, run `uv tool update-shell`
and open a new terminal.

To install from this checkout, use `uv tool install --python 3.12 .`, or
`uv tool install --python 3.12 '.[mcp]'` for the optional local stdio MCP server.
The base distribution has no MCP dependency. See the
[installation guide](docs/guides/installation.md) for MCP installation from
GitHub, updates, and removal.

## Develop ASC OS

```console
uv sync --frozen --all-groups --all-extras
uv run asc-os --version
uv run asc-os doctor --json
```

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

License: Apache-2.0. See the [release guide](docs/guides/releases.md) for local
release preparation and validation. Publication requires explicit maintainer
authorization under the repository policy.
