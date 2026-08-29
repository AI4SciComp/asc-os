# ADR 0007: MCP security boundary

Status: accepted, 2026-08-29.

The current official [Model Context Protocol specification](https://modelcontextprotocol.io/specification/2026-07-28)
revision was retrieved on 2026-08-29 (SHA-256
`8b970114bafcf6f2f3066572ab18f5069fe28db55ddbb72842628692894bad49`).
ASC OS uses the stable official Python SDK 2.1.1 from signed upstream commit
`0921d94a74db900dccd2d534842aa7b6160542d2`; its exact lock entry is in
`uv.lock` and its license is MIT.

The server uses `MCPServer`, an explicit project root, validated tool schemas,
and stdio only. Resources, prompts, and tools are tested through both an
in-process `Client` and `StdioServerParameters`. No token store, listener,
shell, Python execution, Git mutation, credentials, or network-fetch surface is
present. Tool errors are concise and do not log full research content.
