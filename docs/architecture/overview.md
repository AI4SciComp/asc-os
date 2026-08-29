# Architecture overview

ASC OS separates authored truth from derived views:

- `research/` contains versioned authored manifests;
- `.ai/generated/` contains content-addressed context projections;
- `research/runs/` contains immutable lifecycle event records;
- `build/` contains reproducible gluing and artifact manifests.

The service layer validates schemas, references, hashes, policies, and paths.
The typed Python API, CLI, and MCP server are adapters over the same services.
No adapter calls an LLM in v0.1.

The lifecycle is `explore -> cover/plan -> execute -> verify -> glue ->
project`. Execution belongs to a human or external harness; ASC OS freezes
inputs and records declared outputs.

The topos-inspired vocabulary is deliberately modest: contexts are bounded
research regions, restriction compiles only relevant state, overlaps declare
compatibility checks, and gluing emits an integration manifest. These analogies
do not prove semantic completeness or mathematical correctness.
