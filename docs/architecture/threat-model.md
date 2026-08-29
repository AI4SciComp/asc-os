# Threat model

Untrusted inputs include YAML/JSON manifests, paths, MCP arguments, generated
file ownership claims, and external evidence metadata.

Controls include safe YAML loading, byte/depth limits, duplicate-key rejection,
Draft 2020-12 schemas, typed references, project-root confinement, output
symlink rejection, exclusive locks, temporary-file `fsync` and atomic replace,
content hashes, and fixed overlap operations.

The MCP server starts with an explicit project root and accepts only stdio. It
does not expose arbitrary shell or Python, Git mutation, credential access,
network fetching, or a listening socket. External evidence URIs are recorded
but never fetched. Skills are validated as external, untrusted descriptions and
are not imported.

Residual risks include compromised local dependencies, malicious code outside
ASC OS invoked by a human, filesystem semantics that weaken durability, and
incorrect but schema-valid research assertions. Review, provenance, and direct
tests remain required.
