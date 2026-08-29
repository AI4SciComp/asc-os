# Claims and evidence

A claim records a bounded statement, assumptions, dependencies, evidence, and
projection labels. A `verified` status requires resolved verified evidence,
required evidence classes, matching local checksums, and a current material
input snapshot. Changed assumptions, evidence, dependencies, contexts, or active
decisions mark the claim stale.

Evidence types distinguish derivations, formal proofs, tests, benchmarks,
literature, reviews, and builds. External URIs are recorded but not fetched.
