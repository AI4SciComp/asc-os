"""Integration tests for declared covers and safe overlap checks."""

from pathlib import Path

import pytest

from asc_os.errors import UnsafePathError
from asc_os.scaffold import init_project, scaffold_manifest
from asc_os.verification import check_cover, check_overlap


def _verification_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    init_project(root)
    scaffold_manifest(
        root,
        "context",
        "CTX-CHILD",
        "Child",
        parent="CTX-ROOT",
    )
    scaffold_manifest(root, "claim", "CLM-ONE", "Claim")
    claim = root / "research" / "claims" / "CLM-ONE.yaml"
    claim.write_text(
        claim.read_text(encoding="utf-8").replace(
            "status: draft",
            "status: active",
        ),
        encoding="utf-8",
    )
    (root / "left.yaml").write_text(
        "scalar: same\nset: [alpha, beta]\nordered: [first, second]\n",
        encoding="utf-8",
    )
    (root / "right.yaml").write_text(
        "scalar: same\nset: [beta, alpha]\nordered: [first, second]\n",
        encoding="utf-8",
    )
    overlap = root / "research" / "overlaps" / "OVL-ONE.yaml"
    overlap.write_text(
        """\
api_version: ai4scicomp.research/v1
kind: ResearchOverlap
metadata:
  id: OVL-ONE
  title: Complete built-in overlap vocabulary
  status: active
  labels: []
spec:
  left: CTX-ROOT
  right: CTX-CHILD
  checks:
    - id: scalar
      type: value_equal
      left: {file: left.yaml, pointer: /scalar}
      right: {file: right.yaml, pointer: /scalar}
    - id: set
      type: set_equal
      left: {file: left.yaml, pointer: /set}
      right: {file: right.yaml, pointer: /set}
    - id: ordered
      type: ordered_list_equal
      left: {file: left.yaml, pointer: /ordered}
      right: {file: right.yaml, pointer: /ordered}
    - id: hash
      type: content_hash_equal
      left: {file: research/notation.yaml}
      right: {file: research/notation.yaml}
    - id: reference
      type: reference_resolves
      reference: CTX-ROOT
      kind: ResearchContext
    - id: schema
      type: schema_valid
      left: {file: research/project.yaml}
    - id: status
      type: claim_status_at_least
      reference: CLM-ONE
      minimum_status: active
    - id: file
      type: file_exists
      left: {file: research/assumptions.yaml}
  failure_policy: block_gluing
""",
        encoding="utf-8",
    )
    cover = root / "research" / "covers" / "COV-ONE.yaml"
    cover.write_text(
        """\
api_version: ai4scicomp.research/v1
kind: ResearchCover
metadata:
  id: COV-ONE
  title: Declared cover
  status: active
  labels: []
spec:
  target: CTX-ROOT
  members: [CTX-CHILD]
  requirements:
    deliverable: [CTX-CHILD]
  required_overlaps: [OVL-ONE]
""",
        encoding="utf-8",
    )
    return root


def test_all_eight_overlap_check_types_pass(tmp_path: Path) -> None:
    root = _verification_project(tmp_path)
    report = check_overlap(root, "OVL-ONE")
    assert report.passed
    assert {item.check_type for item in report.checks} == {
        "value_equal",
        "set_equal",
        "ordered_list_equal",
        "content_hash_equal",
        "reference_resolves",
        "schema_valid",
        "claim_status_at_least",
        "file_exists",
    }
    assert all(item.passed for item in report.checks)


def test_overlap_reports_compatibility_failure(tmp_path: Path) -> None:
    root = _verification_project(tmp_path)
    right = root / "right.yaml"
    right.write_text(
        right.read_text(encoding="utf-8").replace(
            "scalar: same", "scalar: other"
        ),
        encoding="utf-8",
    )
    report = check_overlap(root, "OVL-ONE")
    assert not report.passed
    failed = [item for item in report.checks if not item.passed]
    assert [(item.check_id, item.message) for item in failed] == [
        ("scalar", "Values differ.")
    ]


def test_cover_checks_declared_matrix_and_boundaries(tmp_path: Path) -> None:
    root = _verification_project(tmp_path)
    report = check_cover(root, "COV-ONE")
    assert report.passed
    assert all(item.passed for item in report.checks)


def test_cover_rejects_requirement_outside_members(tmp_path: Path) -> None:
    root = _verification_project(tmp_path)
    cover = root / "research" / "covers" / "COV-ONE.yaml"
    cover.write_text(
        cover.read_text(encoding="utf-8").replace(
            "deliverable: [CTX-CHILD]",
            "deliverable: [CTX-ROOT]",
        ),
        encoding="utf-8",
    )
    report = check_cover(root, "COV-ONE")
    assert not report.passed
    assert "CTX-ROOT" in next(
        item.message for item in report.checks if not item.passed
    )


def test_file_exists_reports_missing_file(tmp_path: Path) -> None:
    root = _verification_project(tmp_path)
    overlap = root / "research" / "overlaps" / "OVL-ONE.yaml"
    overlap.write_text(
        overlap.read_text(encoding="utf-8").replace(
            "research/assumptions.yaml}",
            "research/missing.yaml}",
        ),
        encoding="utf-8",
    )
    report = check_overlap(root, "OVL-ONE")
    outcome = next(item for item in report.checks if item.check_id == "file")
    assert not outcome.passed
    assert outcome.message.endswith("does not exist.")


def test_overlap_rejects_symlink_escape(tmp_path: Path) -> None:
    root = _verification_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "value.yaml").write_text("scalar: same\n", encoding="utf-8")
    (root / "outside-link").symlink_to(outside, target_is_directory=True)
    overlap = root / "research" / "overlaps" / "OVL-ONE.yaml"
    overlap.write_text(
        overlap.read_text(encoding="utf-8").replace(
            "left.yaml, pointer: /scalar",
            "outside-link/value.yaml, pointer: /scalar",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(UnsafePathError):
        check_overlap(root, "OVL-ONE")


def test_schema_valid_check_reports_invalid_manifest(tmp_path: Path) -> None:
    root = _verification_project(tmp_path)
    overlap = root / "research" / "overlaps" / "OVL-ONE.yaml"
    overlap.write_text(
        overlap.read_text(encoding="utf-8").replace(
            "research/project.yaml}",
            "left.yaml}",
        ),
        encoding="utf-8",
    )
    report = check_overlap(root, "OVL-ONE")
    outcome = next(item for item in report.checks if item.check_id == "schema")
    assert not outcome.passed
    assert "Unsupported api_version" in outcome.message
