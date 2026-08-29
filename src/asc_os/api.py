"""Typed service API shared by the CLI and MCP adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from asc_os.errors import AscOSError, ErrorDetail, ExitCode
from asc_os.manifest import ProjectState, load_project_state
from asc_os.provenance import check_claim, scan_staleness
from asc_os.skills import validate_skill
from asc_os.verification import check_cover, check_overlap


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Deterministic project-validation result."""

    valid: bool
    project_root: str
    manifest_count: int
    errors: tuple[dict[str, object], ...] = ()
    exit_code: int = 0

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
            exit_code=int(error.exit_code),
        )
    errors: list[tuple[ErrorDetail, ExitCode]] = []
    staleness = scan_staleness(state.root)
    if staleness.stale:
        errors.append(
            (
                ErrorDetail(
                    code="stale_derived_state",
                    message="Stale records: " + ", ".join(staleness.stale),
                    hint="Rebuild or reverify each stale derived record.",
                ),
                ExitCode.STALE,
            )
        )
    for cover in state.by_kind("ResearchCover"):
        if not check_cover(state.root, cover.id).passed:
            errors.append(  # noqa: PERF401
                (
                    ErrorDetail(
                        code="cover_check_failed",
                        message=f"Declared cover {cover.id!r} does not pass.",
                        path=str(cover.path),
                        hint="Correct the cover matrix and boundaries.",
                    ),
                    ExitCode.COMPATIBILITY_FAILED,
                )
            )
    for overlap in state.by_kind("ResearchOverlap"):
        if not check_overlap(state.root, overlap.id).passed:
            errors.append(  # noqa: PERF401
                (
                    ErrorDetail(
                        code="overlap_check_failed",
                        message=f"Overlap {overlap.id!r} does not pass.",
                        path=str(overlap.path),
                        hint="Correct the declared compatibility operands.",
                    ),
                    ExitCode.COMPATIBILITY_FAILED,
                )
            )
    for claim in state.by_kind("ResearchClaim"):
        report = check_claim(state.root, claim.id)
        if not report.passed and not report.stale:
            errors.append(
                (
                    ErrorDetail(
                        code="claim_evidence_policy_failed",
                        message=f"Claim {claim.id!r} does not satisfy policy.",
                        path=str(claim.path),
                        hint=(
                            "Resolve evidence status, class, and integrity "
                            "checks."
                        ),
                    ),
                    ExitCode.EVIDENCE_POLICY,
                )
            )
    for skill in state.by_kind("ResearchSkill"):
        if not validate_skill(state.root, skill.id).passed:
            errors.append(  # noqa: PERF401
                (
                    ErrorDetail(
                        code="skill_schema_invalid",
                        message=f"Skill {skill.id!r} does not validate.",
                        path=str(skill.path),
                        hint="Correct its referenced Draft 2020-12 schemas.",
                    ),
                    ExitCode.SCHEMA_INVALID,
                )
            )
    if errors:
        priority = (
            ExitCode.STALE
            if any(code == ExitCode.STALE for _detail, code in errors)
            else errors[0][1]
        )
        return ValidationReport(
            valid=False,
            project_root=str(state.root),
            manifest_count=len(state.manifests),
            errors=tuple(asdict(detail) for detail, _code in errors),
            exit_code=int(priority),
        )
    return ValidationReport(
        valid=True,
        project_root=str(state.root),
        manifest_count=len(state.manifests),
    )
