"""Project discovery and path-confinement utilities."""

from __future__ import annotations

import os
from pathlib import Path, PurePath

from asc_os.errors import (
    ErrorDetail,
    ExitCode,
    ProjectNotFoundError,
    UnsafePathError,
)


def find_project_root(start: str | Path = ".") -> Path:
    """Find the nearest ancestor containing ``research/project.yaml``.

    Args:
        start: File or directory from which to begin discovery.

    Returns:
        The absolute project root.

    Raises:
        ProjectNotFoundError: If no project root exists.

    """
    candidate = Path(start).expanduser().absolute()
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if (directory / "research" / "project.yaml").is_file():
            return directory
    raise ProjectNotFoundError(os.fspath(candidate))


def confined_path(
    root: Path,
    value: str | Path,
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve a project-relative path and prove it stays under ``root``.

    Args:
        root: Trusted project root.
        value: Untrusted project-relative path.
        must_exist: Whether the result must already exist.

    Returns:
        A normalized absolute path within ``root``.

    Raises:
        UnsafePathError: If the path is absolute, traverses, escapes through a
            symlink, or is missing when required.

    """
    raw = Path(value)
    if raw.is_absolute() or ".." in PurePath(raw).parts:
        raise _unsafe(value, "Use a project-relative path without '..'.")
    resolved_root = root.resolve(strict=True)
    joined = resolved_root / raw
    try:
        resolved = joined.resolve(strict=must_exist)
        resolved.relative_to(resolved_root)
    except (FileNotFoundError, OSError, ValueError) as error:
        raise _unsafe(
            value, "Keep the path inside the project root."
        ) from error
    if must_exist and not resolved.exists():
        raise _unsafe(value, "Choose an existing project path.")
    return resolved


def relative_posix(root: Path, path: Path) -> str:
    """Return a stable POSIX project-relative path."""
    return path.resolve().relative_to(root.resolve()).as_posix()


def _unsafe(value: str | Path, hint: str) -> UnsafePathError:
    return UnsafePathError(
        ErrorDetail(
            code="unsafe_path",
            message="Path is outside the allowed project boundary.",
            path=os.fspath(value),
            hint=hint,
        ),
        ExitCode.UNSAFE_PATH,
    )
