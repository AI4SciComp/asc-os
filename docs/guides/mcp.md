# MCP guide

[Install](installation.md) the optional SDK extra from the GitHub release:

```console
uv tool install --python 3.12 'asc-os[mcp] @ https://github.com/AI4SciComp/asc-os/releases/download/v0.1.0/asc_os-0.1.0-py3-none-any.whl'
```

Then start one explicit project root from any directory:

```console
asc-os mcp serve --transport stdio --project /absolute/project/root
```

Use a process client such as the official Python SDK's
`StdioServerParameters`; do not expose the process as a network service. The
server publishes read-only research resources, seven bounded prompts, and ten
schema-validated tools. Write tools default to dry-run and cannot write outside
the project.

The current SDK/specification evidence is in
[ADR 0007](../architecture/decisions/0007-mcp-security-boundary.md).
