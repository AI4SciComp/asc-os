# Deterministic restriction

Restriction compiles only state relevant to one requested context. It never
loads every project file by default. Material sources receive exact SHA-256
hashes and the entire neutral model receives a canonical content hash.

Evidence summaries and complete declared source excerpts are explicit options.
An output limit reports the largest sections and fails rather than truncating.
