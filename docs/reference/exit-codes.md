# Stable exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Success. |
| 2 | Command-line usage error. |
| 3 | No research project was found. |
| 4 | Schema or manifest validation failed. |
| 5 | A reference was unresolved or invalid. |
| 6 | A cover, overlap, glue, or artifact compatibility check failed. |
| 7 | Generated or evidence-bearing state is stale. |
| 8 | An unsafe path was rejected. |
| 9 | A safe-write conflict was rejected. |
| 10 | The requested API version is unsupported. |
| 11 | Evidence policy failed. |
| 12 | An unexpected internal error reached the command adapter. |

Diagnostics in JSON mode contain a stable machine-readable error code, a
message, and an actionable hint. Success text is written to stdout and human
error text to stderr.
