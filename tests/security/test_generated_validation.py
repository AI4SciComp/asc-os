"""Reject malformed derived data without trusting its recorded hashes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from asc_os.canonical import content_hash
from asc_os.provenance import scan_staleness
from asc_os.scaffold import init_project
from asc_os.storage import generated_json_metadata


def _context(model: dict[str, Any]) -> dict[str, object]:
    return {
        "_asc_os": generated_json_metadata(content_hash(model)),
        "context": model,
    }


@pytest.mark.parametrize(
    "document",
    (
        [],
        {},
        {"_asc_os": {}, "context": {}},
        _context({}),
        _context({"provenance": {}}),
        _context({"provenance": {"source_hashes": {"x": None}}}),
        _context({"provenance": {"source_hashes": {"../outside": "a" * 64}}}),
        _context({"provenance": {"source_hashes": {"missing": "a" * 64}}}),
        _context({"provenance": {"source_hashes": {}}}),
        _context({"provenance": {"source_hashes": {}}, "decisions": [None]}),
        _context({"provenance": {"source_hashes": {}}, "decisions": [{}]}),
    ),
)
def test_invalid_context_bundle_is_stale(
    tmp_path: Path, document: dict[str, Any] | list[object]
) -> None:
    init_project(tmp_path)
    directory = tmp_path / ".ai/generated/common/CTX-ROOT"
    directory.mkdir()
    (directory / "context.json").write_text(json.dumps(document))
    assert scan_staleness(tmp_path).stale == (".ai/generated/common/CTX-ROOT",)


def _projection(hashes: object) -> dict[str, object]:
    body = {"material_hashes": hashes}
    return {"_asc_os": generated_json_metadata(content_hash(body)), **body}


@pytest.mark.parametrize(
    ("document", "stale"),
    (
        ([], False),
        ({}, False),
        ({"material_hashes": {}}, True),
        ({"material_hashes": {}, "_asc_os": {}}, True),
        (_projection({"file": None}), True),
        (_projection({"../outside": "a" * 64}), True),
        (_projection({"missing": "a" * 64}), True),
        (_projection({"RESEARCH.md": "a" * 64}), True),
        (_projection({}), False),
    ),
)
def test_projection_staleness_distinguishes_unmanaged_json(
    tmp_path: Path, document: dict[str, Any] | list[object], stale: bool
) -> None:
    init_project(tmp_path)
    directory = tmp_path / "build"
    directory.mkdir()
    (directory / "projection.json").write_text(json.dumps(document))
    expected = ("build/projection.json",) if stale else ()
    assert scan_staleness(tmp_path).stale == expected


@pytest.mark.parametrize(
    "payload", (b"\xff", b"{", b" " * (8 * 1024 * 1024 + 1))
)
@pytest.mark.parametrize("relative", ("context", "projection"))
def test_unreadable_or_oversized_derived_data_is_stale(
    tmp_path: Path, payload: bytes, relative: str
) -> None:
    init_project(tmp_path)
    if relative == "context":
        target = ".ai/generated/common/CTX-ROOT/context.json"
        expected = ".ai/generated/common/CTX-ROOT"
    else:
        target = "build/projection.json"
        expected = target
    path = tmp_path / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    assert scan_staleness(tmp_path).stale == (expected,)
