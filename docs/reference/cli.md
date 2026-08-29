# CLI reference

The installed command is `asc-os`. All inspection commands support stable text
output, and commands marked with `--json` emit canonical compact JSON.

| Command family | Purpose |
| --- | --- |
| `doctor` | Report the local Python, Git, uv, MCP, and transport state. |
| `init` | Plan or create a research state tree; `--adopt` preserves existing files. |
| `validate` | Validate schemas, references, generated state, and policy. |
| `scaffold` | Plan or create one context, cover, overlap, claim, decision, evidence, or artifact. |
| `context` | List, show, or deterministically build bounded context bundles. |
| `cover`, `overlap` | Inspect and check declared decomposition contracts. |
| `claim`, `decision`, `evidence` | Inspect evidence-bearing research state. |
| `run` | Start, inspect, or finish a lifecycle run record. |
| `glue`, `artifact` | Check or create manifest-only projections. |
| `skill` | List or validate descriptive skill manifests; never execute them. |
| `mcp serve` | Serve the same bounded operations over local stdio. |

Run `asc-os COMMAND --help` for the authoritative arguments. Mutating commands
offer `--dry-run`; MCP mutating tools default to dry-run.

## Canonical identity

- repository and distribution: `asc-os`
- Python import: `asc_os`
- executable: `asc-os`

No compatibility alias is provided for a provisional product name.
