"""Integration tests for gluing and manifest-only artifact projection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from asc_os.errors import (
    CompatibilityError,
    UnsafePathError,
    WriteConflictError,
)
from asc_os.projection import (
    artifact_check,
    create_artifact_manifest,
    create_gluing_manifest,
    glue_check,
)
from asc_os.provenance import scan_staleness
from asc_os.scaffold import init_project, scaffold_manifest


def _load(path: Path) -> dict[str, Any]:
    return cast(
        dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8"))
    )


def _write(path: Path, document: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _ready_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    init_project(root)
    root_context = root / "research" / "contexts" / "root" / "context.yaml"
    document = _load(root_context)
    document["metadata"]["status"] = "active"
    _write(root_context, document)
    scaffold_manifest(
        root,
        "context",
        "CTX-CHILD",
        "Child",
        parent="CTX-ROOT",
    )
    child_context = root / "research" / "contexts" / "child" / "context.yaml"
    document = _load(child_context)
    document["metadata"]["status"] = "completed"
    _write(child_context, document)
    scaffold_manifest(
        root,
        "overlap",
        "OVL-ONE",
        "Compatible overlap",
        left="CTX-ROOT",
        right="CTX-CHILD",
    )
    scaffold_manifest(root, "cover", "COV-ONE", "Complete cover")
    cover_path = root / "research" / "covers" / "COV-ONE.yaml"
    cover = _load(cover_path)
    cover["metadata"]["status"] = "active"
    cover["spec"]["target"] = "CTX-ROOT"
    cover["spec"]["members"] = ["CTX-CHILD"]
    cover["spec"]["requirements"] = {"deliverable": ["CTX-CHILD"]}
    cover["spec"]["required_overlaps"] = ["OVL-ONE"]
    _write(cover_path, cover)
    return root


def test_glue_check_and_manifest_are_deterministic(tmp_path: Path) -> None:
    root = _ready_project(tmp_path)
    assert glue_check(root, "COV-ONE").passed
    preview = create_gluing_manifest(
        root,
        "COV-ONE",
        "build/glue/COV-ONE.json",
        dry_run=True,
    )
    assert not (root / "build").exists()
    first = create_gluing_manifest(
        root,
        "COV-ONE",
        "build/glue/COV-ONE.json",
    )
    payload = (root / "build" / "glue" / "COV-ONE.json").read_bytes()
    second = create_gluing_manifest(
        root,
        "COV-ONE",
        "build/glue/COV-ONE.json",
    )
    assert preview.source_hash == first.source_hash == second.source_hash
    assert second.plan.is_noop
    assert (root / "build" / "glue" / "COV-ONE.json").read_bytes() == payload
    document = cast(dict[str, Any], json.loads(payload))
    assert document["kind"] == "GluingManifest"
    assert "merge" not in document


def test_glue_fails_on_unready_context(tmp_path: Path) -> None:
    root = _ready_project(tmp_path)
    child_path = root / "research" / "contexts" / "child" / "context.yaml"
    child = _load(child_path)
    child["metadata"]["status"] = "draft"
    _write(child_path, child)
    report = glue_check(root, "COV-ONE")
    assert not report.passed
    with pytest.raises(CompatibilityError) as caught:
        create_gluing_manifest(root, "COV-ONE", "build/glue.json")
    assert caught.value.detail.code == "glue_prerequisites_failed"


def test_glue_fails_on_incompatible_overlap(tmp_path: Path) -> None:
    root = _ready_project(tmp_path)
    overlap_path = root / "research" / "overlaps" / "OVL-ONE.yaml"
    overlap = _load(overlap_path)
    overlap["spec"]["checks"][0]["left"]["file"] = "missing.yaml"
    _write(overlap_path, overlap)
    report = glue_check(root, "COV-ONE")
    outcome = next(
        item for item in report.checks if item.check_id == "overlap:OVL-ONE"
    )
    assert not outcome.passed


def test_artifact_projection_is_manifest_only(tmp_path: Path) -> None:
    root = _ready_project(tmp_path)
    scaffold_manifest(
        root,
        "artifact",
        "ART-PAPER",
        "Illustrative paper",
        artifact_type="paper",
    )
    artifact_path = root / "research" / "artifacts" / "ART-PAPER.yaml"
    artifact = _load(artifact_path)
    artifact["metadata"]["status"] = "active"
    artifact["spec"]["contexts"] = ["CTX-ROOT", "CTX-CHILD"]
    artifact["spec"]["output_contract"]["path"] = (
        "build/artifacts/paper-manifest.json"
    )
    _write(artifact_path, artifact)
    assert artifact_check(root, "ART-PAPER").passed
    operation = create_artifact_manifest(root, "ART-PAPER")
    output = root / "build" / "artifacts" / "paper-manifest.json"
    document = cast(
        dict[str, Any], json.loads(output.read_text(encoding="utf-8"))
    )
    assert operation.record_id == "ART-PAPER"
    assert document["kind"] == "ArtifactProjectionManifest"
    assert document["output_contract"]["format"] == "manifest_only"
    assert not (root / "build" / "artifacts" / "paper.md").exists()


def test_missing_artifact_evidence_class_blocks_projection(
    tmp_path: Path,
) -> None:
    root = _ready_project(tmp_path)
    scaffold_manifest(root, "artifact", "ART-ONE", "Artifact")
    artifact_path = root / "research" / "artifacts" / "ART-ONE.yaml"
    artifact = _load(artifact_path)
    artifact["spec"]["required_evidence_classes"] = ["benchmark"]
    _write(artifact_path, artifact)
    report = artifact_check(root, "ART-ONE")
    assert not report.passed
    with pytest.raises(CompatibilityError):
        create_artifact_manifest(root, "ART-ONE")


def test_generated_output_roots_and_external_opt_in(tmp_path: Path) -> None:
    root = _ready_project(tmp_path)
    with pytest.raises(CompatibilityError) as unapproved:
        create_gluing_manifest(root, "COV-ONE", "reports/glue.json")
    assert unapproved.value.detail.code == "unapproved_output_root"
    outside = tmp_path / "gluing.json"
    with pytest.raises(UnsafePathError):
        create_gluing_manifest(root, "COV-ONE", outside)
    operation = create_gluing_manifest(
        root,
        "COV-ONE",
        outside,
        allow_external_output=True,
    )
    assert operation.plan.root == tmp_path
    assert outside.is_file()


def test_generated_manifest_never_overwrites_hand_authored_output(
    tmp_path: Path,
) -> None:
    root = _ready_project(tmp_path)
    output = root / "build" / "glue.json"
    output.parent.mkdir()
    output.write_text("human\n", encoding="utf-8")
    with pytest.raises(WriteConflictError):
        create_gluing_manifest(root, "COV-ONE", "build/glue.json", force=True)
    assert output.read_text(encoding="utf-8") == "human\n"


def test_changed_material_requires_force_for_owned_manifest(
    tmp_path: Path,
) -> None:
    root = _ready_project(tmp_path)
    output = "build/glue.json"
    first = create_gluing_manifest(root, "COV-ONE", output)
    notation = root / "research" / "notation.yaml"
    notation.write_text("symbols: {epsilon: illustrative}\n", encoding="utf-8")
    assert scan_staleness(root).stale == ("build/glue.json",)
    with pytest.raises(WriteConflictError):
        create_gluing_manifest(root, "COV-ONE", output)
    replaced = create_gluing_manifest(root, "COV-ONE", output, force=True)
    assert replaced.source_hash != first.source_hash
    assert scan_staleness(root).passed
