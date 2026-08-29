# ADR 0006: overlap and gluing

Status: accepted, 2026-08-29.

Overlap contracts permit only `value_equal`, `set_equal`,
`ordered_list_equal`, `content_hash_equal`, `reference_resolves`,
`schema_valid`, `claim_status_at_least`, and `file_exists`. They cannot embed
regular-expression scripts, shell commands, Python expressions, or templates.

Gluing succeeds only after cover, context status, overlap, evidence policy, and
staleness checks pass. Its result is a deterministic manifest; it never invokes
Git merge or alters a source branch. Artifact projection is likewise
manifest-only and never invents publication prose.
