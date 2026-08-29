# MCP guide

Install the optional SDK extra, then start one explicit project root:

```console
pip install 'asc-os[mcp]'
asc-os mcp serve --transport stdio --project /absolute/project/root
```

Use a process client such as the official Python SDK's
`StdioServerParameters`; do not expose the process as a network service. The
server publishes read-only research resources, seven bounded prompts, and ten
schema-validated tools. Write tools default to dry-run and cannot write outside
the project.

The current SDK/specification evidence is in
[ADR 0007](../architecture/decisions/0007-mcp-security-boundary.md).
