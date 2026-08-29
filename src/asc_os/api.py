"""Typed service API shared by the CLI and MCP adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from asc_os.errors import AscOSError
from asc_os.manifest import ProjectState, load_project_state


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Deterministic project-validation result."""

    valid: bool
    project_root: str
    manifest_count: int
    errors: tuple[dict[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible report."""
        return asdict(self)


def load_project(path: str | Path = ".") -> ProjectState:
    """Load and fully validate an authored research project.

    Args:
        path: Project root or a descendant path.

    Returns:
        The typed, reference-validated project state.

    """
    return load_project_state(path)


def validate_project(path: str | Path = ".") -> ValidationReport:
    """Validate a project without mutating it.

    Args:
        path: Project root or a descendant path.

    Returns:
        A deterministic validation report.

    """
    try:
        state = load_project(path)
    except AscOSError as error:
        return ValidationReport(
            valid=False,
            project_root=str(Path(path).absolute()),
            manifest_count=0,
            errors=(asdict(error.detail),),
        )
    return ValidationReport(
        valid=True,
        project_root=str(state.root),
        manifest_count=len(state.manifests),
    )
