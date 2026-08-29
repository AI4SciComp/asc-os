# ASC OS documentation

```{toctree}
:maxdepth: 2

architecture/overview
architecture/threat-model
architecture/repository-boundaries
architecture/decisions/0001-project-identity
architecture/decisions/0002-topos-inspired-model
architecture/decisions/0003-schema-and-canonicalization
architecture/decisions/0004-storage-and-provenance
architecture/decisions/0005-context-compilation
architecture/decisions/0006-overlap-and-gluing
architecture/decisions/0007-mcp-security-boundary
architecture/decisions/0008-skill-contract-without-code-execution
concepts/contexts
concepts/covers
concepts/restrictions
concepts/overlaps
concepts/claims-and-evidence
concepts/gluing-and-projections
guides/quickstart
guides/codex
guides/claude-code
guides/mcp
guides/migration
reference/cli
reference/schemas
reference/exit-codes
reference/compatibility-checks
```

ASC OS is a local-first, model-agnostic research-state substrate. It provides
bounded context compilation, validated compatibility, evidence traceability,
and manifest-only integration without arbitrary execution.

Architecture decisions are recorded under
[`docs/architecture/decisions`](architecture/decisions/0001-project-identity.md).
