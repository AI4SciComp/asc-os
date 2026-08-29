# Compatibility checks

Overlap manifests declare a fixed vocabulary of checks; they never contain
code. v0.1 supports exact value equality, canonical hash equality, JSON Pointer
equality, and required-file presence. Inputs are project-relative, confined,
and locally loaded.

A cover passes only when all members resolve and all required overlaps pass.
Gluing additionally requires ready contexts, non-stale claims, acceptable
evidence, and successful overlap checks. A gluing manifest records those
results; it does not merge code or scientific data.

Failures identify the overlap and check ID and report the incompatible values
without silently choosing a winner. The deliberately incompatible pilot
fixture demonstrates the diagnostic contract.
