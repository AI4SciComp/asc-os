# ADR 0004: storage and provenance

Status: accepted, 2026-08-29.

Authored research state is never overwritten by scaffolding or generation.
Write operations validate a complete plan, acquire an exclusive project lock,
write and `fsync` a same-filesystem temporary file, atomically replace, and
best-effort `fsync` the parent. Generated replacement requires ASC OS ownership
metadata; lifecycle finish uses a compare-before-replace hash.

Evidence records store immutable URIs, checksums, media types, limitations, and
optional producer runs. External resources are not fetched. Derived manifests
record all material input hashes so validation can report staleness.
