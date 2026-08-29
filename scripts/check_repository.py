"""Enforce repository identity, boundary, and tracked-file policies."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

_CANONICAL_IDENTITIES = ("asc-os", "asc_os")
_RETIRED_OR_REMOVED = (
    "asc-" + "research-os",
    "asc_" + "research",
    "asc-" + "xde-py",
    "asc-" + "mathcopilot",
    "asc-" + "lab",
)
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)
_BINARY_SUFFIXES = {".gif", ".ico", ".jpeg", ".jpg", ".pdf", ".png"}


def _tracked_files(repository: Path) -> tuple[Path, ...]:
    """Return tracked and staged repository files in stable order."""
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git is required for the repository policy check")
    result = subprocess.run(  # noqa: S603 - fixed executable and arguments.
        [git, "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        repository / name
        for name in sorted(filter(None, result.stdout.splitlines()))
    )


def main() -> int:
    """Reject noncanonical names, C++, secret material, and unsafe surfaces."""
    repository = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    identities = set(_CANONICAL_IDENTITIES)
    if identities != {"asc-os", "asc_os"}:
        failures.append("canonical identity configuration changed")
    for path in _tracked_files(repository):
        relative = path.relative_to(repository).as_posix()
        if path.suffix.lower() in {".cc", ".cpp", ".cxx", ".h", ".hpp"}:
            failures.append(f"C++ is outside v0.1 scope: {relative}")
        if path.suffix.lower() in _BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        failures.extend(
            f"retired or removed name {name}: {relative}"
            for name in _RETIRED_OR_REMOVED
            if name in text or name in relative
        )
        failures.extend(
            f"secret-shaped value: {relative}"
            for pattern in _SECRET_PATTERNS
            if pattern.search(text)
        )
        lowered = text.lower()
        if relative in {
            "src/asc_os/cli.py",
            "src/asc_os/mcp_server.py",
            "src/asc_os/skills.py",
        } and any(
            token in lowered
            for token in ("subprocess.run", "os.system(", "shell=true")
        ):
            failures.append(f"arbitrary execution surface: {relative}")
    if failures:
        raise SystemExit("\n".join(failures))
    print("canonical names, repository boundary, and secret scan: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
