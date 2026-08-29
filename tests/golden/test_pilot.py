"""End-to-end golden tests for the synthetic AP kinetic pilot."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, cast

import anyio
from mcp import Client

from asc_os.api import validate_project
from asc_os.context import build_context
from asc_os.mcp_server import create_server
from asc_os.projection import (
    create_artifact_manifest,
    create_gluing_manifest,
    glue_check,
)
from asc_os.provenance import check_claim
from asc_os.verification import check_cover, check_overlap

_SOURCE = Path(__file__).resolve().parents[2] / "examples" / "ap-kinetic-study"
_ARTIFACTS = ("ART-PAPER", "ART-PROPOSAL", "ART-CODE", "ART-DATASET")
_OVERLAPS = (
    "OVL-MODEL-ASYMPTOTIC",
    "OVL-ASYMPTOTIC-ORBIT",
    "OVL-ORBIT-SEMILAGRANGIAN",
    "OVL-SEMILAGRANGIAN-ANALYSIS",
    "OVL-ANALYSIS-EXPERIMENTS",
)


def _pilot(tmp_path: Path) -> Path:
    destination = tmp_path / "ap-kinetic-study"
    shutil.copytree(_SOURCE, destination)
    return destination


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pilot_validates_and_declared_compatibility_passes(
    tmp_path: Path,
) -> None:
    root = _pilot(tmp_path)
    report = validate_project(root)
    assert report.valid
    assert report.manifest_count == 27
    assert check_cover(root, "COV-0001").passed
    assert all(check_overlap(root, item).passed for item in _OVERLAPS)
    assert glue_check(root, "COV-0001").passed


def test_orbit_codex_bundle_matches_golden_hashes_byte_for_byte(
    tmp_path: Path,
) -> None:
    root = _pilot(tmp_path)
    expected = cast(
        dict[str, Any],
        json.loads(
            (root / "expected" / "golden-hashes.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    first = build_context(root, "CTX-ORBIT", harness="codex")
    assert first.source_hash == expected["source_sha256"]
    files = cast(dict[str, str], expected["files"])
    assert {path: _sha256(root / path) for path in files} == files
    second = build_context(root, "CTX-ORBIT", harness="codex")
    assert second.plan.is_noop
    assert {path: _sha256(root / path) for path in files} == files


def test_deliberate_overlap_fixture_fails_precisely(tmp_path: Path) -> None:
    root = _pilot(tmp_path)
    fixture = root / "expected" / "incompatible-overlap.yaml"
    destination = root / "research" / "overlaps" / "OVL-ASYMPTOTIC-ORBIT.yaml"
    destination.write_bytes(fixture.read_bytes())
    report = check_overlap(root, "OVL-ASYMPTOTIC-ORBIT")
    assert not report.passed
    assert [(item.check_id, item.message) for item in report.checks] == [
        ("deliberate-limit-mismatch", "Values differ.")
    ]


def test_material_change_marks_pilot_claims_stale(tmp_path: Path) -> None:
    root = _pilot(tmp_path)
    assumptions = root / "research" / "assumptions.yaml"
    assumptions.write_text(
        assumptions.read_text(encoding="utf-8")
        + "  - id: ASM-CHANGED\n"
        + "    statement: Deliberate stale-input mutation.\n",
        encoding="utf-8",
    )
    assert check_claim(root, "CLM-LIMIT-SYSTEM").stale
    assert check_claim(root, "CLM-ORBIT-AP").stale


def test_pilot_generates_glue_and_four_artifact_manifests(
    tmp_path: Path,
) -> None:
    root = _pilot(tmp_path)
    glue = create_gluing_manifest(
        root,
        "COV-0001",
        "build/glue/COV-0001.json",
    )
    assert len(glue.source_hash) == 64
    operations = [create_artifact_manifest(root, item) for item in _ARTIFACTS]
    assert all(len(item.source_hash) == 64 for item in operations)
    assert sorted(
        path.name for path in (root / "build" / "artifacts").iterdir()
    ) == [
        "code-manifest.json",
        "dataset-manifest.json",
        "paper-manifest.json",
        "proposal-manifest.json",
    ]
    second = create_gluing_manifest(
        root,
        "COV-0001",
        "build/glue/COV-0001.json",
    )
    assert second.plan.is_noop


def test_pilot_state_is_exposed_through_mcp(tmp_path: Path) -> None:
    root = _pilot(tmp_path)

    async def scenario() -> None:
        async with Client(create_server(root), raise_exceptions=True) as client:
            context = await client.read_resource(
                "research://contexts/CTX-ORBIT"
            )
            assert "CTX-ORBIT" in cast(Any, context.contents[0]).text
            overlap = await client.call_tool(
                "check_overlap", {"overlap_id": "OVL-ASYMPTOTIC-ORBIT"}
            )
            payload = cast(dict[str, Any], overlap.structured_content)
            assert payload["passed"] is True

    anyio.run(scenario)
