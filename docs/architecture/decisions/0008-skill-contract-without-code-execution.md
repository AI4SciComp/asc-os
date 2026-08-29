# ADR 0008: descriptive skills without execution

Status: accepted, 2026-08-29.

A v0.1 skill declares a version, capabilities, required context fields, input
and output JSON Schemas, and `execution: {mode: external, trusted: false}`.
ASC OS validates these records and Draft 2020-12 schemas but never imports a
package, evaluates manifest content, or launches a command. A future executable
skill design requires a separate threat model and API version.
