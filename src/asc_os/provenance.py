"""Evidence integrity, claim policy, and decision staleness analysis."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from asc_os.canonical import content_hash, file_hash
from asc_os.errors import UnsafePathError
from asc_os.manifest import Manifest, ProjectState, load_project_state
from asc_os.paths import confined_path, relative_posix
from asc_os.verification import CheckOutcome

_MAX_DERIVED_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class EvidenceSourceOutcome:
    """Integrity result for one evidence source."""

    uri: str
    checked: bool
    passed: bool
    expected_sha256: str
    actual_sha256: str | None
    message: str


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    """Evidence manifest and source-integrity report."""

    evidence_id: str
    evidence_type: str
    status: str
    passed: bool
    sources: tuple[EvidenceSourceOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable report data."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ClaimReport:
    """Claim evidence-policy and staleness report."""

    claim_id: str
    status: str
    passed: bool
    stale: bool
    expected_input_hashes: Mapping[str, str]
    recorded_input_hashes: Mapping[str, str]
    checks: tuple[CheckOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable report data."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InvalidationReport:
    """Records potentially affected by one or more superseding decisions."""

    decisions: tuple[str, ...]
    contexts: tuple[str, ...]
    claims: tuple[str, ...]
    overlaps: tuple[str, ...]
    artifacts: tuple[str, ...]
    bundles: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable report data."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StalenessReport:
    """Actual derived staleness plus conservative decision invalidations."""

    stale: tuple[str, ...]
    potential: InvalidationReport

    @property
    def passed(self) -> bool:
        """Whether no actually stale record was found."""
        return not self.stale

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable report data."""
        return {
            "passed": self.passed,
            "stale": list(self.stale),
            "potential": self.potential.to_dict(),
        }


def inspect_evidence(
    project_path: str | Path,
    evidence_id: str,
) -> EvidenceReport:
    """Inspect checksums for local sources without fetching external URIs."""
    state = load_project_state(project_path)
    evidence = state.require(evidence_id, "ResearchEvidence")
    sources = cast(Iterable[Mapping[str, Any]], evidence.spec["sources"])
    outcomes = tuple(_inspect_source(state, source) for source in sources)
    return EvidenceReport(
        evidence.id,
        cast(str, evidence.spec["evidence_type"]),
        evidence.metadata.status,
        all(item.passed for item in outcomes),
        outcomes,
    )


def expected_claim_input_hashes(
    project_path: str | Path,
    claim_id: str,
) -> dict[str, str]:
    """Compute the exact material-input snapshot expected for a claim."""
    state = load_project_state(project_path)
    claim = state.require(claim_id, "ResearchClaim")
    return _expected_claim_input_hashes(state, claim)


def check_claim(
    project_path: str | Path,
    claim_id: str,
) -> ClaimReport:
    """Check evidence policy, source integrity, and verified-state freshness."""
    state = load_project_state(project_path)
    claim = state.require(claim_id, "ResearchClaim")
    evidence = tuple(
        state.require(item, "ResearchEvidence")
        for item in _string_list(claim.spec["evidence"])
    )
    project_policy = _mapping(state.project.spec["policies"])
    requires_evidence = bool(
        project_policy.get("verified_claim_requires_evidence", True)
    )
    required_classes = {
        *_string_list(project_policy.get("required_evidence_classes", ())),
        *_string_list(claim.spec.get("required_evidence_classes", ())),
    }
    available_classes = {
        cast(str, item.spec["evidence_type"]) for item in evidence
    }
    checks: list[CheckOutcome] = []
    verified = claim.metadata.status == "verified"
    evidence_present = bool(evidence) or not requires_evidence or not verified
    checks.append(
        CheckOutcome(
            "evidence-present",
            "claim_evidence_policy",
            evidence_present,
            (
                f"{len(evidence)} evidence record(s) resolve."
                if evidence_present
                else "A verified claim requires at least one evidence record."
            ),
        )
    )
    missing_classes = tuple(sorted(required_classes - available_classes))
    class_policy = not verified or not missing_classes
    checks.append(
        CheckOutcome(
            "evidence-classes",
            "claim_evidence_classes",
            class_policy,
            (
                "All required evidence classes are present."
                if class_policy
                else "Missing evidence classes: " + ", ".join(missing_classes)
            ),
        )
    )
    evidence_reports = tuple(
        _inspect_evidence_manifest(state, item) for item in evidence
    )
    evidence_integrity = all(item.passed for item in evidence_reports)
    evidence_status = not verified or all(
        item.metadata.status == "verified" for item in evidence
    )
    checks.extend(
        (
            CheckOutcome(
                "evidence-integrity",
                "claim_evidence_integrity",
                evidence_integrity,
                (
                    "Evidence source integrity checks pass."
                    if evidence_integrity
                    else "At least one evidence source checksum fails."
                ),
            ),
            CheckOutcome(
                "evidence-status",
                "claim_evidence_status",
                evidence_status,
                (
                    "Evidence status is sufficient."
                    if evidence_status
                    else "Verified claims require verified evidence records."
                ),
            ),
        )
    )
    expected = _expected_claim_input_hashes(state, claim)
    recorded = {
        str(key): str(value)
        for key, value in _mapping(claim.spec.get("input_hashes", {})).items()
    }
    stale = verified and recorded != expected
    checks.append(
        CheckOutcome(
            "material-inputs",
            "claim_staleness",
            not stale,
            (
                "Material input hashes match the verification snapshot."
                if not stale
                else "Verified claim input hashes are missing or stale."
            ),
        )
    )
    ordered = tuple(sorted(checks, key=lambda item: item.check_id))
    return ClaimReport(
        claim.id,
        claim.metadata.status,
        all(item.passed for item in ordered),
        stale,
        expected,
        recorded,
        ordered,
    )


def decision_invalidation(
    project_path: str | Path,
    decision_id: str | None = None,
) -> InvalidationReport:
    """Identify records potentially affected by decision supersession."""
    state = load_project_state(project_path)
    decisions = (
        (state.require(decision_id, "ResearchDecision"),)
        if decision_id is not None
        else tuple(
            item
            for item in state.by_kind("ResearchDecision")
            if item.spec["supersedes"]
        )
    )
    superseded = {
        reference
        for item in decisions
        for reference in _string_list(item.spec["supersedes"])
    }
    affected_contexts = {
        context_id
        for item in decisions
        for context_id in _string_list(item.spec["affected_contexts"])
    }
    for reference in superseded:
        old = state.require(reference, "ResearchDecision")
        affected_contexts.update(_string_list(old.spec["affected_contexts"]))
    affected_claims = {
        item.id
        for item in state.by_kind("ResearchClaim")
        if cast(str, item.spec["context"]) in affected_contexts
    }
    affected_overlaps = {
        item.id
        for item in state.by_kind("ResearchOverlap")
        if cast(str, item.spec["left"]) in affected_contexts
        or cast(str, item.spec["right"]) in affected_contexts
    }
    affected_artifacts = {
        item.id
        for item in state.by_kind("ResearchArtifact")
        if affected_contexts.intersection(_string_list(item.spec["contexts"]))
        or affected_claims.intersection(_string_list(item.spec["claims"]))
    }
    bundles = tuple(
        sorted(
            f".ai/generated/common/{context_id}"
            for context_id in affected_contexts
            if (
                state.root / ".ai" / "generated" / "common" / context_id
            ).is_dir()
        )
    )
    return InvalidationReport(
        tuple(sorted(item.id for item in decisions)),
        tuple(sorted(affected_contexts)),
        tuple(sorted(affected_claims)),
        tuple(sorted(affected_overlaps)),
        tuple(sorted(affected_artifacts)),
        bundles,
    )


def scan_staleness(project_path: str | Path) -> StalenessReport:
    """Scan verified claims and common context bundles for staleness."""
    state = load_project_state(project_path)
    stale: set[str] = set()
    for claim in state.by_kind("ResearchClaim"):
        if claim.metadata.status == "verified":
            expected = _expected_claim_input_hashes(state, claim)
            recorded = {
                str(key): str(value)
                for key, value in _mapping(
                    claim.spec.get("input_hashes", {})
                ).items()
            }
            if recorded != expected:
                stale.add(claim.id)
    generated = state.root / ".ai" / "generated" / "common"
    if generated.is_dir():
        for path in sorted(generated.glob("*/context.json")):
            if _context_bundle_is_stale(state, path):
                stale.add(relative_posix(state.root, path.parent))
    return StalenessReport(
        tuple(sorted(stale)),
        decision_invalidation(state.root),
    )


def _inspect_evidence_manifest(
    state: ProjectState,
    evidence: Manifest,
) -> EvidenceReport:
    sources = cast(Iterable[Mapping[str, Any]], evidence.spec["sources"])
    outcomes = tuple(_inspect_source(state, source) for source in sources)
    return EvidenceReport(
        evidence.id,
        cast(str, evidence.spec["evidence_type"]),
        evidence.metadata.status,
        all(item.passed for item in outcomes),
        outcomes,
    )


def _inspect_source(
    state: ProjectState,
    source: Mapping[str, Any],
) -> EvidenceSourceOutcome:
    uri = cast(str, source["uri"])
    expected = cast(str, source["sha256"])
    parsed = urlsplit(uri)
    if parsed.scheme != "file":
        valid = bool(parsed.scheme)
        return EvidenceSourceOutcome(
            uri,
            False,
            valid,
            expected,
            None,
            (
                "External source recorded; network retrieval is intentionally "
                "disabled."
                if valid
                else "Evidence URI has no scheme."
            ),
        )
    if parsed.netloc or not parsed.path:
        return EvidenceSourceOutcome(
            uri,
            False,
            False,
            expected,
            None,
            "Local evidence URI must be file: followed by a relative path.",
        )
    path = confined_path(state.root, parsed.path)
    if not path.is_file():
        return EvidenceSourceOutcome(
            uri,
            True,
            False,
            expected,
            None,
            "Local evidence file does not exist.",
        )
    actual = file_hash(path)
    return EvidenceSourceOutcome(
        uri,
        True,
        actual == expected,
        expected,
        actual,
        (
            "Local evidence checksum matches."
            if actual == expected
            else "Local evidence checksum does not match."
        ),
    )


def _expected_claim_input_hashes(
    state: ProjectState,
    claim: Manifest,
) -> dict[str, str]:
    definition = claim.to_dict()
    metadata = cast(dict[str, Any], definition["metadata"])
    metadata.pop("status", None)
    metadata.pop("updated_at", None)
    spec = cast(dict[str, Any], definition["spec"])
    spec.pop("input_hashes", None)
    material: dict[str, str] = {
        "claim_definition": content_hash(definition),
    }
    context = state.require(cast(str, claim.spec["context"]), "ResearchContext")
    paths = {
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
        context.path,
    }
    for reference in _string_list(claim.spec["depends_on"]):
        paths.add(state.require(reference, "ResearchClaim").path)
    for reference in _string_list(claim.spec["evidence"]):
        evidence = state.require(reference, "ResearchEvidence")
        paths.add(evidence.path)
        sources = cast(Iterable[Mapping[str, Any]], evidence.spec["sources"])
        for source in sources:
            uri = cast(str, source["uri"])
            parsed = urlsplit(uri)
            if parsed.scheme == "file" and not parsed.netloc and parsed.path:
                source_path = confined_path(state.root, parsed.path)
                key = (
                    f"evidence-source:{relative_posix(state.root, source_path)}"
                )
                material[key] = (
                    file_hash(source_path)
                    if source_path.is_file()
                    else content_hash({"missing": parsed.path})
                )
            else:
                material[f"evidence-uri:{uri}"] = cast(str, source["sha256"])
    for decision in state.by_kind("ResearchDecision"):
        if decision.metadata.status == "active" and context.id in _string_list(
            decision.spec["affected_contexts"]
        ):
            paths.add(decision.path)
    for path in sorted(paths):
        confined = confined_path(
            state.root,
            path.absolute().relative_to(state.root.absolute()),
            must_exist=True,
        )
        material[relative_posix(state.root, confined)] = file_hash(confined)
    return dict(sorted(material.items()))


def _context_bundle_is_stale(  # noqa: PLR0911
    state: ProjectState,
    path: Path,
) -> bool:
    try:
        payload = path.read_bytes()
        if len(payload) > _MAX_DERIVED_BYTES:
            return True
        parsed: object = json.loads(payload.decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return True
    if not isinstance(parsed, dict):
        return True
    document = cast(dict[str, Any], parsed)
    raw_metadata = document.get("_asc_os")
    model = document.get("context")
    if not isinstance(raw_metadata, Mapping) or not isinstance(model, Mapping):
        return True
    metadata = cast(Mapping[str, Any], raw_metadata)
    model_mapping = cast(Mapping[str, Any], model)
    source_hash = metadata.get("source_sha256")
    if not isinstance(source_hash, str) or content_hash(model) != source_hash:
        return True
    raw_provenance = model_mapping.get("provenance")
    if not isinstance(raw_provenance, Mapping):
        return True
    provenance = cast(Mapping[str, Any], raw_provenance)
    raw_recorded = provenance.get("source_hashes")
    if not isinstance(raw_recorded, Mapping):
        return True
    recorded = cast(Mapping[str, Any], raw_recorded)
    for relative, expected in recorded.items():
        if not isinstance(expected, str):
            return True
        try:
            source_path = confined_path(state.root, relative, must_exist=True)
        except UnsafePathError:
            return True
        if file_hash(source_path) != expected:
            return True
    context_id = path.parent.name
    current_decisions = {
        item.id
        for item in state.by_kind("ResearchDecision")
        if item.metadata.status == "active"
        and context_id in _string_list(item.spec["affected_contexts"])
    }
    raw_decisions = model_mapping.get("decisions")
    if not isinstance(raw_decisions, list):
        return True
    decision_values = cast(list[object], raw_decisions)
    if not all(isinstance(item, Mapping) for item in decision_values):
        return True
    decisions = cast(list[Mapping[str, Any]], decision_values)
    if not all(isinstance(item.get("id"), str) for item in decisions):
        return True
    recorded_decisions = {cast(str, item["id"]) for item in decisions}
    return current_decisions != recorded_decisions


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value)


def _string_list(value: object) -> tuple[str, ...]:
    return tuple(cast(Iterable[str], value))
