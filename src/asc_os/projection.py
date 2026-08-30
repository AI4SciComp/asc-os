"""Non-mutating glue checks and deterministic manifest-only projections."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path, PurePath
from typing import Any, cast

from asc_os.canonical import canonical_json, content_hash, file_hash
from asc_os.errors import CompatibilityError, ErrorDetail, ExitCode
from asc_os.manifest import Manifest, ProjectState, load_project_state
from asc_os.paths import confined_path, relative_posix
from asc_os.provenance import check_claim, scan_staleness
from asc_os.storage import PlannedWrite, WritePlan, apply_plan
from asc_os.verification import CheckOutcome, check_cover, check_overlap

_READY_CONTEXT_STATUSES = frozenset({"active", "completed"})


@dataclass(frozen=True, slots=True)
class GlueReport:
    """Prerequisite report for one declared cover."""

    cover_id: str
    passed: bool
    checks: tuple[CheckOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable report data."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ArtifactReport:
    """Prerequisite report for one artifact projection."""

    artifact_id: str
    artifact_type: str
    passed: bool
    checks: tuple[CheckOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable report data."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ManifestOperation:
    """Deterministic generated manifest plus exact write plan."""

    record_id: str
    source_hash: str
    plan: WritePlan

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable operation data."""
        return {
            "record_id": self.record_id,
            "source_hash": self.source_hash,
            "plan": self.plan.to_dict(),
        }


def glue_check(project_path: str | Path, cover_id: str) -> GlueReport:
    """Check every explicit gluing prerequisite without merging source."""
    state = load_project_state(project_path)
    cover = state.require(cover_id, "ResearchCover")
    context_ids = {
        cast(str, cover.spec["target"]),
        *_string_list(cover.spec["members"]),
    }
    outcomes: list[CheckOutcome] = []
    cover_report = check_cover(state.root, cover_id)
    outcomes.append(
        CheckOutcome(
            "cover",
            "glue_cover",
            cover_report.passed,
            (
                "Declared cover checks pass."
                if cover_report.passed
                else "Declared cover checks fail."
            ),
        )
    )
    for context_id in sorted(context_ids):
        context = state.require(context_id, "ResearchContext")
        passed = context.metadata.status in _READY_CONTEXT_STATUSES
        outcomes.append(
            CheckOutcome(
                f"context:{context_id}",
                "glue_context_status",
                passed,
                f"Context status {context.metadata.status!r} "
                + ("is ready." if passed else "is not active or completed."),
            )
        )
    for overlap_id in _string_list(cover.spec["required_overlaps"]):
        report = check_overlap(state.root, overlap_id)
        outcomes.append(
            CheckOutcome(
                f"overlap:{overlap_id}",
                "glue_overlap",
                report.passed,
                (
                    "Required overlap checks pass."
                    if report.passed
                    else "Required overlap checks fail."
                ),
            )
        )
    claims = tuple(
        item
        for item in state.by_kind("ResearchClaim")
        if cast(str, item.spec["context"]) in context_ids
    )
    for claim in claims:
        report = check_claim(state.root, claim.id)
        outcomes.append(
            CheckOutcome(
                f"claim:{claim.id}",
                "glue_claim_policy",
                report.passed,
                (
                    "Claim evidence policy and freshness pass."
                    if report.passed
                    else "Claim evidence policy or freshness fails."
                ),
            )
        )
    staleness = scan_staleness(state.root)
    relevant_stale = tuple(
        item
        for item in staleness.stale
        if item in {claim.id for claim in claims}
        or any(context_id in item for context_id in context_ids)
    )
    outcomes.append(
        CheckOutcome(
            "staleness",
            "glue_staleness",
            not relevant_stale,
            (
                "No required derived result is stale."
                if not relevant_stale
                else "Stale required results: " + ", ".join(relevant_stale)
            ),
        )
    )
    ordered = tuple(sorted(outcomes, key=lambda item: item.check_id))
    return GlueReport(cover_id, all(item.passed for item in ordered), ordered)


def artifact_check(
    project_path: str | Path,
    artifact_id: str,
) -> ArtifactReport:
    """Check one artifact's declared contexts, claims, and evidence classes."""
    state = load_project_state(project_path)
    artifact = state.require(artifact_id, "ResearchArtifact")
    outcomes: list[CheckOutcome] = []
    contexts = tuple(
        state.require(item, "ResearchContext")
        for item in _string_list(artifact.spec["contexts"])
    )
    claims = tuple(
        state.require(item, "ResearchClaim")
        for item in _string_list(artifact.spec["claims"])
    )
    for context in contexts:
        passed = context.metadata.status in _READY_CONTEXT_STATUSES
        outcomes.append(
            CheckOutcome(
                f"context:{context.id}",
                "artifact_context_status",
                passed,
                f"Context status {context.metadata.status!r} "
                + ("is ready." if passed else "is not active or completed."),
            )
        )
    for claim in claims:
        report = check_claim(state.root, claim.id)
        outcomes.append(
            CheckOutcome(
                f"claim:{claim.id}",
                "artifact_claim_policy",
                report.passed,
                (
                    "Claim policy and freshness pass."
                    if report.passed
                    else "Claim policy or freshness fails."
                ),
            )
        )
    required_classes = set(
        _string_list(artifact.spec["required_evidence_classes"])
    )
    available_classes = {
        cast(str, evidence.spec["evidence_type"])
        for claim in claims
        for evidence in (
            state.require(item, "ResearchEvidence")
            for item in _string_list(claim.spec["evidence"])
        )
    }
    missing = tuple(sorted(required_classes - available_classes))
    outcomes.append(
        CheckOutcome(
            "evidence-classes",
            "artifact_evidence_classes",
            not missing,
            (
                "All artifact evidence classes are present."
                if not missing
                else "Missing artifact evidence classes: " + ", ".join(missing)
            ),
        )
    )
    staleness = scan_staleness(state.root)
    stale_claims = tuple(
        item.id for item in claims if item.id in staleness.stale
    )
    outcomes.append(
        CheckOutcome(
            "staleness",
            "artifact_staleness",
            not stale_claims,
            (
                "No artifact claim is stale."
                if not stale_claims
                else "Stale artifact claims: " + ", ".join(stale_claims)
            ),
        )
    )
    ordered = tuple(sorted(outcomes, key=lambda item: item.check_id))
    return ArtifactReport(
        artifact.id,
        cast(str, artifact.spec["artifact_type"]),
        all(item.passed for item in ordered),
        ordered,
    )


def create_gluing_manifest(
    project_path: str | Path,
    cover_id: str,
    output: str | Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    allow_external_output: bool = False,
) -> ManifestOperation:
    """Create a deterministic integration manifest without source mutation."""
    state = load_project_state(project_path)
    report = glue_check(state.root, cover_id)
    if not report.passed:
        raise _compatibility_error(
            "glue_prerequisites_failed",
            f"Cover {cover_id!r} is not ready for gluing.",
        )
    cover = state.require(cover_id, "ResearchCover")
    material = _cover_material_hashes(state, cover)
    body: dict[str, Any] = {
        "api_version": "ai4scicomp.glue/v1",
        "kind": "GluingManifest",
        "cover_id": cover_id,
        "contexts": sorted(
            {
                cast(str, cover.spec["target"]),
                *_string_list(cover.spec["members"]),
            }
        ),
        "overlaps": sorted(_string_list(cover.spec["required_overlaps"])),
        "checks": report.to_dict(),
        "material_hashes": material,
    }
    return _write_manifest(
        state,
        cover_id,
        body,
        output,
        dry_run=dry_run,
        force=force,
        allow_external_output=allow_external_output,
    )


def create_artifact_manifest(
    project_path: str | Path,
    artifact_id: str,
    output: str | Path | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
    allow_external_output: bool = False,
) -> ManifestOperation:
    """Create a deterministic manifest-only artifact projection."""
    state = load_project_state(project_path)
    report = artifact_check(state.root, artifact_id)
    if not report.passed:
        raise _compatibility_error(
            "artifact_prerequisites_failed",
            f"Artifact {artifact_id!r} is not ready for projection.",
        )
    artifact = state.require(artifact_id, "ResearchArtifact")
    output_contract = _mapping(artifact.spec["output_contract"])
    destination = output or cast(str, output_contract["path"])
    body: dict[str, Any] = {
        "api_version": "ai4scicomp.artifact/v1",
        "kind": "ArtifactProjectionManifest",
        "artifact_id": artifact.id,
        "artifact_type": artifact.spec["artifact_type"],
        "contexts": sorted(_string_list(artifact.spec["contexts"])),
        "claims": sorted(_string_list(artifact.spec["claims"])),
        "output_contract": output_contract,
        "checks": report.to_dict(),
        "material_hashes": _artifact_material_hashes(state, artifact),
    }
    return _write_manifest(
        state,
        artifact_id,
        body,
        destination,
        dry_run=dry_run,
        force=force,
        allow_external_output=allow_external_output,
    )


def _write_manifest(
    state: ProjectState,
    record_id: str,
    body: dict[str, Any],
    output: str | Path,
    *,
    dry_run: bool,
    force: bool,
    allow_external_output: bool,
) -> ManifestOperation:
    source_hash = content_hash(body)
    document = {
        "_asc_os": {
            "generator": "asc-os",
            "generator_version": "0.1.0",
            "source_sha256": source_hash,
        },
        **body,
    }
    content = canonical_json(document) + "\n"
    plan = _output_plan(
        state.root,
        output,
        PlannedWrite(
            "placeholder",
            content,
            generated=True,
            source_hash=source_hash,
            allow_replace_owned=force,
        ),
        allow_external_output=allow_external_output,
    )
    effective = apply_plan(plan, dry_run=dry_run)
    return ManifestOperation(record_id, source_hash, effective)


def _output_plan(
    project_root: Path,
    output: str | Path,
    write: PlannedWrite,
    *,
    allow_external_output: bool,
) -> WritePlan:
    raw = Path(output).expanduser()
    if raw.is_absolute():
        if not allow_external_output:
            confined_path(project_root, raw)
        root = raw.parent.absolute()
        return WritePlan(
            root,
            (),
            (
                PlannedWrite(
                    raw.name,
                    write.content,
                    generated=write.generated,
                    source_hash=write.source_hash,
                    allow_replace_owned=write.allow_replace_owned,
                ),
            ),
        )
    if ".." in PurePath(raw).parts or not raw.parts:
        confined_path(project_root, raw)
    approved = raw.parts[0] == "build" or raw.parts[:2] == (
        ".ai",
        "generated",
    )
    if not approved:
        raise _compatibility_error(
            "unapproved_output_root",
            "Generated manifests must use .ai/ or build/ inside the project.",
        )
    relative = raw.as_posix()
    return WritePlan(
        project_root,
        (str(raw.parent),),
        (
            PlannedWrite(
                relative,
                write.content,
                generated=write.generated,
                source_hash=write.source_hash,
                allow_replace_owned=write.allow_replace_owned,
            ),
        ),
    )


def _cover_material_hashes(
    state: ProjectState,
    cover: Manifest,
) -> dict[str, str]:
    context_ids = {
        cast(str, cover.spec["target"]),
        *_string_list(cover.spec["members"]),
    }
    paths = {
        cover.path,
        *(state.require(item, "ResearchContext").path for item in context_ids),
        *(
            state.require(item, "ResearchOverlap").path
            for item in _string_list(cover.spec["required_overlaps"])
        ),
    }
    paths.update(_shared_material_paths(state, context_ids))
    for overlap_id in _string_list(cover.spec["required_overlaps"]):
        overlap = state.require(overlap_id, "ResearchOverlap")
        checks = cast(Iterable[Mapping[str, Any]], overlap.spec["checks"])
        for check in checks:
            for side in ("left", "right"):
                operand = check.get(side)
                if isinstance(operand, Mapping):
                    value = cast(Mapping[str, Any], operand).get("file")
                    if isinstance(value, str):
                        paths.add(
                            confined_path(state.root, value, must_exist=True)
                        )
    claims = tuple(
        item
        for item in state.by_kind("ResearchClaim")
        if cast(str, item.spec["context"]) in context_ids
    )
    paths.update(item.path for item in claims)
    for claim in claims:
        for evidence_id in _string_list(claim.spec["evidence"]):
            evidence = state.require(evidence_id, "ResearchEvidence")
            paths.update(_evidence_paths(state, evidence))
    return _hash_paths(state, paths)


def _artifact_material_hashes(
    state: ProjectState,
    artifact: Manifest,
) -> dict[str, str]:
    context_ids = set(_string_list(artifact.spec["contexts"]))
    paths = {
        artifact.path,
        *(state.require(item, "ResearchContext").path for item in context_ids),
    }
    paths.update(_shared_material_paths(state, context_ids))
    for claim_id in _string_list(artifact.spec["claims"]):
        claim = state.require(claim_id, "ResearchClaim")
        paths.add(claim.path)
        for evidence_id in _string_list(claim.spec["evidence"]):
            evidence = state.require(evidence_id, "ResearchEvidence")
            paths.update(_evidence_paths(state, evidence))
    return _hash_paths(state, paths)


def _shared_material_paths(
    state: ProjectState,
    context_ids: set[str],
) -> set[Path]:
    paths = {
        state.project.path,
        confined_path(
            state.root,
            cast(str, state.project.spec["notation"]),
            must_exist=True,
        ),
        confined_path(
            state.root,
            cast(str, state.project.spec["assumptions"]),
            must_exist=True,
        ),
    }
    paths.update(
        item.path
        for item in state.by_kind("ResearchDecision")
        if item.metadata.status == "active"
        and context_ids.intersection(
            _string_list(item.spec["affected_contexts"])
        )
    )
    return paths


def _evidence_paths(state: ProjectState, evidence: Manifest) -> set[Path]:
    paths = {evidence.path}
    sources = cast(Iterable[Mapping[str, Any]], evidence.spec["sources"])
    for source in sources:
        uri = cast(str, source["uri"])
        if uri.startswith("file:"):
            candidate = confined_path(state.root, uri.removeprefix("file:"))
            if candidate.is_file():
                paths.add(candidate)
    return paths


def _hash_paths(
    state: ProjectState,
    paths: Iterable[Path],
) -> dict[str, str]:
    return {
        relative_posix(state.root, path): file_hash(path)
        for path in sorted(set(paths))
    }


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value)


def _string_list(value: object) -> tuple[str, ...]:
    return tuple(cast(Iterable[str], value))


def _compatibility_error(code: str, message: str) -> CompatibilityError:
    return CompatibilityError(
        ErrorDetail(
            code=code,
            message=message,
            hint="Resolve the reported prerequisites before generating output.",
        ),
        ExitCode.COMPATIBILITY_FAILED,
    )
