# Changelog

## 0.1.0 — unreleased

- Document user-wide installation with uv tools, including the optional MCP
  extra, PATH setup, upgrades, and removal.
- Verify installed distributions in isolated tool environments outside the
  checkout, including bundled schemas and project discovery from subdirectories.
- Use the package version in generated context and projection manifests.
- Recognize current and development-version generated JSON during explicit
  forced regeneration, preserving ownership and path checks.
- Include tests and the dependency lockfile in the source distribution.
- Enforce the 90% branch coverage requirement separately from total coverage,
  with direct tests for installed schemas and malformed generated data.
- Add versioned research manifests and safe reference validation.
- Add deterministic context bundles, declared cover and overlap checks.
- Add evidence policy, staleness, lifecycle, gluing, and artifact manifests.
- Add the typed Python API, complete CLI, and local stdio MCP server.
- Add a synthetic end-to-end pilot and reproducible golden checks.
