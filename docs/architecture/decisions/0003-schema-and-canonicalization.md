# ADR 0003: schemas, style, and canonicalization

Status: accepted, 2026-08-29.

Manifests use YAML for authoring and JSON Schema Draft 2020-12 under
`ai4scicomp.research/v1`. Canonical hashes use normalized line endings, sorted
object keys, explicit set-like normalization, compact UTF-8 JSON, finite
numbers, and SHA-256. Stable v1 breakage requires a new API version.

The official [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
was retrieved on 2026-08-29 (Last-Modified 2026-06-03; SHA-256
`9b02fa0d1aa05bfc8a4b5a95d3594665124f7a0414c82a69359f4a0b2f65e1c0`).
Public APIs are typed and use Google-style docstrings. Ruff, Pylint, strict
Pyright, and comprehensive tests enforce the local contract.

Direct runtime choices are PyYAML 6.0.3, jsonschema 4.26.0, and referencing
0.37.0 under compatible MIT licenses. Exact resolution lives in `uv.lock`.
