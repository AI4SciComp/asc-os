"""Integration tests for safe project and manifest scaffolding."""

from pathlib import Path

import pytest

from asc_os.api import load_project
from asc_os.errors import WriteConflictError
from asc_os.scaffold import init_project, scaffold_manifest


def test_new_project_initializes_and_validates(tmp_path: Path) -> None:
    root = tmp_path / "project"
    applied = init_project(root)
    state = load_project(root)
    assert not applied.is_noop
    assert state.project.id == "PRJ-0001"
    assert state.require("CTX-ROOT").kind == "ResearchContext"
    assert init_project(root, adopt=True).is_noop


def test_dry_run_initialization_has_no_side_effect(tmp_path: Path) -> None:
    root = tmp_path / "project"
    plan = init_project(root, dry_run=True)
    assert plan.writes
    assert not root.exists()


def test_nonempty_project_requires_adopt(tmp_path: Path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    existing = root / "AGENTS.md"
    existing.write_text("# Existing instructions\n", encoding="utf-8")
    with pytest.raises(WriteConflictError) as caught:
        init_project(root)
    assert caught.value.detail.code == "adopt_required"
    init_project(root, adopt=True)
    assert existing.read_text(encoding="utf-8") == "# Existing instructions\n"
    assert (root / "research" / "project.yaml").is_file()


def test_scaffold_context_is_dry_run_capable_and_valid(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    relative = "research/contexts/child/context.yaml"
    preview = scaffold_manifest(
        root,
        "context",
        "CTX-CHILD",
        "Child context",
        parent="CTX-ROOT",
        dry_run=True,
    )
    assert preview.writes[0].path == relative
    assert not (root / relative).exists()
    scaffold_manifest(
        root,
        "context",
        "CTX-CHILD",
        "Child context",
        parent="CTX-ROOT",
    )
    assert load_project(root).require("CTX-CHILD").metadata.title == (
        "Child context"
    )


def test_scaffold_refuses_changed_hand_authored_manifest(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    init_project(root)
    path = root / "research" / "claims" / "CLM-ONE.yaml"
    path.write_text("human: true\n", encoding="utf-8")
    with pytest.raises(WriteConflictError) as caught:
        scaffold_manifest(root, "claim", "CLM-ONE", "One claim")
    assert caught.value.detail.code == "hand_authored_conflict"
    assert path.read_text(encoding="utf-8") == "human: true\n"
