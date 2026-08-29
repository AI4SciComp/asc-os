# Security policy

ASC OS is pre-release. Report vulnerabilities privately with GitHub's security
advisory workflow when available. Do not include credentials, private datasets,
or exploit details in a public issue.

Supported security boundaries include safe YAML loading, schema limits, path
confinement, symlink rejection for outputs, ownership-checked atomic writes,
fixed overlap operations, non-executing skills, and local stdio MCP. The server
has no arbitrary shell, Python, Git mutation, credential, network-fetch, or
network-listener capability.

Security fixes require regression tests. Releases and public advisories are
maintainer decisions and are not automated by CI.
