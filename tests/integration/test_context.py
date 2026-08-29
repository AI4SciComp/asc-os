"""Integration tests for deterministic restricted context bundles."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from asc_os.context import ContextBuildResult, Harness, build_context
from asc_os.errors import ContextBuildError, WriteConflictError
from asc_os.scaffold import init_project, scaffold_manifest


def _planned_content(result: ContextBuildResult, path: str) -> str:
    return next(
        item.content for item in result.plan.writes if item.path == path
    )


def _generated_files(root: Path) -> dict[str, bytes]:
    generated = root / ".ai" / "generated"
    return {
        path.relative_to(generated).as_posix(): path.read_bytes()
        for path in sorted(generated.rglob("*"))
        if path.is_file()
    }


def test_common_dry_run_is_bounded_and_nonmutating(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    result = build_context(root, "CTX-ROOT", dry_run=True)
    paths = {item.path for item in result.plan.writes}
    assert paths == {
        ".ai/generated/common/CTX-ROOT/context.json",
        ".ai/generated/common/CTX-ROOT/context.md",
        ".ai/generated/common/CTX-ROOT/provenance.json",
        ".ai/generated/common/CTX-ROOT/source-hashes.json",
    }
    assert not any((root / ".ai" / "generated" / "common").iterdir())
    for item in result.plan.writes:
        assert os.fspath(root) not in item.content


def test_codex_bundle_is_byte_reproducible(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    first = build_context(root, "CTX-ROOT", harness="codex")
    first_bytes = _generated_files(root)
    second = build_context(root, "CTX-ROOT", harness="codex")
    assert len(first_bytes) == 7
    assert not first.plan.is_noop
    assert second.plan.is_noop
    assert _generated_files(root) == first_bytes
    assert second.source_hash == first.source_hash


def test_changed_input_requires_force_for_owned_output(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    first = build_context(root, "CTX-ROOT", harness="claude")
    context = root / "research" / "contexts" / "root" / "context.yaml"
    context.write_text(
        context.read_text(encoding="utf-8").replace(
            "Define the bounded question.",
            "What changed?",
        ),
        encoding="utf-8",
    )
    with pytest.raises(WriteConflictError):
        build_context(root, "CTX-ROOT", harness="claude")
    replaced = build_context(root, "CTX-ROOT", harness="claude", force=True)
    assert replaced.source_hash != first.source_hash
    assert "What changed?" in (
        root / ".ai" / "generated" / "common" / "CTX-ROOT" / "context.md"
    ).read_text(encoding="utf-8")


def test_evidence_summary_is_opt_in(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    scaffold_manifest(root, "claim", "CLM-ONE", "Claim one")
    scaffold_manifest(root, "evidence", "EVD-ONE", "Evidence one")
    claim = root / "research" / "claims" / "CLM-ONE.yaml"
    claim.write_text(
        claim.read_text(encoding="utf-8").replace(
            "evidence: []",
            "evidence:\n  - EVD-ONE",
        ),
        encoding="utf-8",
    )
    evidence = root / "research" / "evidence" / "EVD-ONE" / "manifest.yaml"
    evidence.write_text(
        evidence.read_text(encoding="utf-8").replace(
            "supports: []",
            "supports:\n  - CLM-ONE",
        ),
        encoding="utf-8",
    )
    without = build_context(root, "CTX-ROOT", dry_run=True)
    with_summary = build_context(
        root,
        "CTX-ROOT",
        include_evidence_summary=True,
        dry_run=True,
    )
    path = ".ai/generated/common/CTX-ROOT/context.json"
    without_payload = cast(
        dict[str, Any], json.loads(_planned_content(without, path))
    )
    with_payload = cast(
        dict[str, Any], json.loads(_planned_content(with_summary, path))
    )
    assert without_payload["context"]["evidence"] == []
    assert with_payload["context"]["evidence"][0]["id"] == "EVD-ONE"


def test_source_excerpt_is_complete_or_build_fails(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    context = root / "research" / "contexts" / "root" / "context.yaml"
    context.write_text(
        context.read_text(encoding="utf-8").replace(
            "files: []",
            "files:\n      - notes.txt",
        ),
        encoding="utf-8",
    )
    (root / "notes.txt").write_text(
        "complete equation: x = y\n", encoding="utf-8"
    )
    result = build_context(
        root,
        "CTX-ROOT",
        include_source_excerpts=True,
        dry_run=True,
    )
    assert "complete equation: x = y" in _planned_content(
        result, ".ai/generated/common/CTX-ROOT/context.json"
    )
    with pytest.raises(ContextBuildError) as caught:
        build_context(
            root,
            "CTX-ROOT",
            include_source_excerpts=True,
            max_bytes=10,
            dry_run=True,
        )
    assert caught.value.detail.code == "source_excerpt_too_large"
    assert not any((root / ".ai" / "generated" / "common").iterdir())


def test_existing_root_instruction_is_never_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    agents = root / "AGENTS.md"
    previous = agents.read_bytes()
    result = build_context(
        root,
        "CTX-ROOT",
        harness="codex",
        install_entrypoint=True,
    )
    assert "AGENTS.md" not in {item.path for item in result.plan.writes}
    assert agents.read_bytes() == previous


def test_explicit_missing_entrypoint_install_is_idempotent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    init_project(root)
    (root / "AGENTS.md").unlink()
    first = build_context(
        root,
        "CTX-ROOT",
        harness="codex",
        install_entrypoint=True,
    )
    second = build_context(
        root,
        "CTX-ROOT",
        harness="codex",
        install_entrypoint=True,
    )
    assert "AGENTS.md" in {item.path for item in first.plan.writes}
    assert second.plan.is_noop


def test_invalid_harness_and_oversize_bundle_fail(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    with pytest.raises(ContextBuildError) as invalid:
        build_context(
            root,
            "CTX-ROOT",
            harness=cast(Harness, "other"),
            dry_run=True,
        )
    assert invalid.value.detail.code == "unsupported_harness"
    with pytest.raises(ContextBuildError) as oversize:
        build_context(root, "CTX-ROOT", max_bytes=10, dry_run=True)
    assert oversize.value.detail.code == "context_size_exceeded"
    assert "content was not truncated" in cast(str, oversize.value.detail.hint)


def test_git_dirty_state_ignores_generated_bundle(tmp_path: Path) -> None:
    executable = shutil.which("git")
    if executable is None:
        pytest.skip("git is unavailable")
    root = tmp_path / "project"
    init_project(root)
    commands = (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=ASC OS Test",
            "-c",
            "user.email=asc-os@example.invalid",
            "commit",
            "-qm",
            "initial",
        ),
    )
    for arguments in commands:
        subprocess.run(  # noqa: S603
            (executable, "-C", os.fspath(root), *arguments),
            check=True,
            capture_output=True,
            timeout=10,
        )
    first = build_context(root, "CTX-ROOT", harness="codex")
    second = build_context(root, "CTX-ROOT", harness="codex")
    assert first.source_hash == second.source_hash
    assert second.plan.is_noop
