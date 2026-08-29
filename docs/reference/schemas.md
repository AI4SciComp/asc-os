# Schema reference

All manifests use `api_version: ai4scicomp.research/v1`, a documented `kind`,
and typed metadata. The bundled JSON Schemas are the executable authority.

| Kind | Typical location | Responsibility |
| --- | --- | --- |
| `ResearchProject` | `research/project.yaml` | Project identity, policy, and root context. |
| `ResearchContext` | `research/contexts/` | Bounded instructions, inputs, outputs, and acceptance criteria. |
| `ResearchCover` | `research/covers/` | Declared context decomposition. |
| `ResearchOverlap` | `research/overlaps/` | Pairwise compatibility checks. |
| `ResearchClaim` | `research/claims/` | Claim status and required evidence. |
| `ResearchDecision` | `research/decisions/` | Decision lifecycle and invalidation inputs. |
| `ResearchEvidence` | `research/evidence/` | Typed evidence with local content addressing. |
| `ResearchRun` | `research/runs/` | Explore-through-project execution history. |
| `ResearchArtifact` | `research/artifacts/` | Manifest-only paper, proposal, code, or dataset projection. |
| `ResearchSkill` | `research/skills/` | Descriptive input/output contracts without execution. |
| `GeneratedOwnership` | generated bundle metadata | Generator, schema, and source hashes. |

Unknown fields are rejected. References are resolved only after every manifest
passes its schema. Canonical hashes are SHA-256 over sorted, UTF-8 canonical
JSON and are independent of YAML presentation.
