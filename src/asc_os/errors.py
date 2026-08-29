"""Stable ASC OS error types and exit codes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ExitCode(IntEnum):
    """Stable process exit codes."""

    SUCCESS = 0
    USAGE = 2
    PROJECT_NOT_FOUND = 3
    SCHEMA_INVALID = 4
    REFERENCE_INVALID = 5
    COMPATIBILITY_FAILED = 6
    STALE = 7
    UNSAFE_PATH = 8
    WRITE_CONFLICT = 9
    UNSUPPORTED_API = 10
    EVIDENCE_POLICY = 11
    INTERNAL = 12


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    """Machine-readable error detail."""

    code: str
    message: str
    path: str | None = None
    hint: str | None = None


class AscOSError(Exception):
    """Base exception carrying a stable exit code and remediation detail."""

    def __init__(
        self,
        detail: ErrorDetail,
        exit_code: ExitCode = ExitCode.INTERNAL,
    ) -> None:
        """Initialize an error with stable machine-readable detail."""
        super().__init__(detail.message)
        self.detail = detail
        self.exit_code = exit_code


class ProjectNotFoundError(AscOSError):
    """Raised when no research project root can be discovered."""

    def __init__(self, path: str) -> None:
        """Initialize the missing-root error for ``path``."""
        super().__init__(
            ErrorDetail(
                code="project_not_found",
                message="No research/project.yaml was found.",
                path=path,
                hint="Run 'asc-os init PATH' or choose a project path.",
            ),
            ExitCode.PROJECT_NOT_FOUND,
        )


class ManifestError(AscOSError):
    """Raised for unsafe or invalid manifest data."""


class ReferenceIntegrityError(AscOSError):
    """Raised for duplicate, unresolved, or cyclic references."""


class UnsafePathError(AscOSError):
    """Raised when a path escapes its project root or output policy."""


class WriteConflictError(AscOSError):
    """Raised when a safe write cannot acquire ownership or a lock."""


class ContextBuildError(AscOSError):
    """Raised when a deterministic context bundle cannot be constructed."""
