"""Integration tests for evidence, claim policy, and staleness."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from asc_os.context import build_context
from asc_os.errors import UnsafePathError
from asc_os.provenance import (
    check_claim,
    decision_invalidation,
    expected_claim_input_hashes,
    inspect_evidence,
    scan_staleness,
)
from asc_os.scaffold import init_project, scaffold_manifest


def _load_document(path: Path) -> dict[str, Any]:
    return cast(
        dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8"))
    )


def _write_document(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )


def _verified_claim_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    init_project(root)
    result_path = root / "results" / "evidence.json"
    result_path.parent.mkdir()
    result_path.write_text('{"passed":true}\n', encoding="utf-8")
    digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
    scaffold_manifest(root, "claim", "CLM-ONE", "Verified claim")
    scaffold_manifest(
        root,
        "evidence",
        "EVD-ONE",
        "Unit-test evidence",
        evidence_type="unit_test",
    )
    claim_path = root / "research" / "claims" / "CLM-ONE.yaml"
    claim = _load_document(claim_path)
    claim["metadata"]["status"] = "verified"
    claim["spec"]["evidence"] = ["EVD-ONE"]
    claim["spec"]["required_evidence_classes"] = ["unit_test"]
    claim["spec"]["input_hashes"] = {}
    _write_document(claim_path, claim)
    evidence_path = root / "research" / "evidence" / "EVD-ONE" / "manifest.yaml"
    evidence = _load_document(evidence_path)
    evidence["metadata"]["status"] = "verified"
    evidence["spec"]["sources"] = [
        {
            "uri": "file:results/evidence.json",
            "sha256": digest,
            "media_type": "application/json",
        }
    ]
    evidence["spec"]["supports"] = ["CLM-ONE"]
    _write_document(evidence_path, evidence)
    claim = _load_document(claim_path)
    claim["spec"]["input_hashes"] = expected_claim_input_hashes(root, "CLM-ONE")
    _write_document(claim_path, claim)
    return root


def test_verified_claim_policy_and_checksums_pass(tmp_path: Path) -> None:
    root = _verified_claim_project(tmp_path)
    evidence = inspect_evidence(root, "EVD-ONE")
    claim = check_claim(root, "CLM-ONE")
    assert evidence.passed
    assert evidence.sources[0].checked
    assert claim.passed
    assert not claim.stale
    assert claim.recorded_input_hashes == claim.expected_input_hashes


def test_material_assumption_change_marks_verified_claim_stale(
    tmp_path: Path,
) -> None:
    root = _verified_claim_project(tmp_path)
    assumptions = root / "research" / "assumptions.yaml"
    assumptions.write_text("assumptions: [changed]\n", encoding="utf-8")
    report = check_claim(root, "CLM-ONE")
    scan = scan_staleness(root)
    assert report.stale
    assert not report.passed
    assert scan.stale == ("CLM-ONE",)


def test_evidence_content_change_fails_integrity_and_stales_claim(
    tmp_path: Path,
) -> None:
    root = _verified_claim_project(tmp_path)
    (root / "results" / "evidence.json").write_text(
        '{"passed":false}\n', encoding="utf-8"
    )
    evidence = inspect_evidence(root, "EVD-ONE")
    claim = check_claim(root, "CLM-ONE")
    assert not evidence.passed
    assert evidence.sources[0].message == (
        "Local evidence checksum does not match."
    )
    assert claim.stale
    assert not claim.passed


def test_required_evidence_class_is_enforced(tmp_path: Path) -> None:
    root = _verified_claim_project(tmp_path)
    project_path = root / "research" / "project.yaml"
    project = _load_document(project_path)
    project["spec"]["policies"]["required_evidence_classes"] = ["benchmark"]
    _write_document(project_path, project)
    report = check_claim(root, "CLM-ONE")
    outcome = next(
        item for item in report.checks if item.check_id == "evidence-classes"
    )
    assert not outcome.passed
    assert outcome.message == "Missing evidence classes: benchmark"


def test_external_evidence_is_recorded_but_never_fetched(
    tmp_path: Path,
) -> None:
    root = _verified_claim_project(tmp_path)
    evidence_path = root / "research" / "evidence" / "EVD-ONE" / "manifest.yaml"
    evidence = _load_document(evidence_path)
    evidence["spec"]["sources"] = [
        {
            "uri": "https://example.invalid/immutable.json",
            "sha256": "a" * 64,
            "media_type": "application/json",
        }
    ]
    _write_document(evidence_path, evidence)
    report = inspect_evidence(root, "EVD-ONE")
    assert report.passed
    assert not report.sources[0].checked
    assert "intentionally disabled" in report.sources[0].message


def test_evidence_path_rejects_symlink_escape(tmp_path: Path) -> None:
    root = _verified_claim_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evidence.json").write_text("{}\n", encoding="utf-8")
    (root / "outside-link").symlink_to(outside, target_is_directory=True)
    evidence_path = root / "research" / "evidence" / "EVD-ONE" / "manifest.yaml"
    evidence = _load_document(evidence_path)
    evidence["spec"]["sources"][0]["uri"] = "file:outside-link/evidence.json"
    _write_document(evidence_path, evidence)
    with pytest.raises(UnsafePathError):
        inspect_evidence(root, "EVD-ONE")


def test_context_bundle_staleness_detects_changed_source(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    init_project(root)
    build_context(root, "CTX-ROOT")
    assert scan_staleness(root).passed
    (root / "research" / "notation.yaml").write_text(
        "symbols: {changed: true}\n",
        encoding="utf-8",
    )
    report = scan_staleness(root)
    assert report.stale == (".ai/generated/common/CTX-ROOT",)


def test_decision_supersession_identifies_affected_records(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    init_project(root)
    scaffold_manifest(root, "claim", "CLM-ONE", "Claim")
    scaffold_manifest(root, "artifact", "ART-ONE", "Artifact")
    scaffold_manifest(root, "decision", "DEC-OLD", "Old")
    scaffold_manifest(root, "decision", "DEC-NEW", "New")
    old_path = root / "research" / "decisions" / "DEC-OLD.yaml"
    old = _load_document(old_path)
    old["metadata"]["status"] = "superseded"
    old["spec"]["affected_contexts"] = ["CTX-ROOT"]
    _write_document(old_path, old)
    new_path = root / "research" / "decisions" / "DEC-NEW.yaml"
    new = _load_document(new_path)
    new["metadata"]["status"] = "active"
    new["spec"]["supersedes"] = ["DEC-OLD"]
    new["spec"]["affected_contexts"] = ["CTX-ROOT"]
    _write_document(new_path, new)
    artifact_path = root / "research" / "artifacts" / "ART-ONE.yaml"
    artifact = _load_document(artifact_path)
    artifact["spec"]["contexts"] = ["CTX-ROOT"]
    _write_document(artifact_path, artifact)
    build_context(root, "CTX-ROOT")
    report = decision_invalidation(root, "DEC-NEW")
    assert report.decisions == ("DEC-NEW",)
    assert report.contexts == ("CTX-ROOT",)
    assert report.claims == ("CLM-ONE",)
    assert report.artifacts == ("ART-ONE",)
    assert report.bundles == (".ai/generated/common/CTX-ROOT",)
