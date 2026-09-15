# Installation

ASC OS supports Python 3.12 through 3.14. Install
[uv](https://docs.astral.sh/uv/getting-started/installation/) first.

## Install from a checkout

Run once from the ASC OS checkout:

```console
uv tool install --python 3.12 .
```

The equivalent convenience target is `make install`. From another directory,
use an absolute path:

```console
uv tool install --python 3.12 /absolute/path/to/asc-os
```

[uv tools](https://docs.astral.sh/uv/guides/tools/#installing-tools) install
the command into a persistent, isolated environment and expose it on your
user PATH. This is a non-editable installation: moving or deleting the source
checkout does not remove the installed command. Schemas and templates are
included in the distribution. Source edits require reinstallation.

If `asc-os` is not found, run `uv tool update-shell` and open a new terminal.
`uv tool dir --bin` shows the executable directory.

Verify from a directory outside the ASC OS checkout:

```console
asc-os --version
asc-os doctor --json
```

Project commands use your current research directory. They also work from
its descendants by finding the nearest `research/project.yaml`. To validate
a project without changing directory, use `asc-os validate /path/to/study`.
See the [quickstart](quickstart.md) to create a study.

## Optional MCP support

Install the SDK extra from the checkout, including when replacing a base
installation:

```console
uv tool install --python 3.12 '.[mcp]'
```

See the [MCP guide](mcp.md) for the local stdio server command.

## Install a built wheel

Build locally with `make build`, then install the resulting file. For a wheel
downloaded from an authorized release, substitute its actual path:

```console
uv tool install --python 3.12 /path/to/asc_os-0.1.0-py3-none-any.whl
```

For MCP, quote the wheel path with its extra:

```console
uv tool install --python 3.12 '/path/to/asc_os-0.1.0-py3-none-any.whl[mcp]'
```

These commands do not require ASC OS to be published on PyPI.

## Update or remove

After updating the checkout, reinstall from its root:

```console
uv tool install --reinstall --python 3.12 .
```

Use `'.[mcp]'` in place of `.` if you want the MCP extra. For a wheel
installation, install the path to the new wheel instead.

Upgrading from `0.1.0.dev0` changes generated version metadata. Review a context
build with `--force --dry-run` before rebuilding with `--force`; replacement
still requires recognized ASC OS ownership and confined output paths.

Remove the tool with:

```console
uv tool uninstall asc-os
```

Your research projects are independent of the tool installation.

## Development environment

Contributors still use `uv sync --frozen --all-groups --all-extras` and
`uv run` for the checkout's pinned development tools. To expose live source
edits as a command everywhere, opt into `uv tool install --python 3.12 -e .`.
An editable installation requires keeping the checkout at its original path.
