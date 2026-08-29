"""Tests for dry-run planning, ownership, locks, and atomic writes."""

from pathlib import Path

import pytest

from asc_os.errors import UnsafePathError, WriteConflictError
from asc_os.storage import (
    PlannedWrite,
    ProjectLock,
    WritePlan,
    apply_plan,
    generated_marker,
)


def test_dry_run_does_not_create_project(tmp_path: Path) -> None:
    root = tmp_path / "new-project"
    plan = WritePlan(root, ("research",), (PlannedWrite("README.md", "x\n"),))
    effective = apply_plan(plan, dry_run=True)
    assert not root.exists()
    assert effective.to_dict()["noop"] is False


def test_apply_is_atomic_and_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "project"
    plan = WritePlan(
        root, ("research",), (PlannedWrite("research/a.txt", "a\n"),)
    )
    first = apply_plan(plan)
    second = apply_plan(plan)
    assert not first.is_noop
    assert second.is_noop
    assert (root / "research" / "a.txt").read_text(encoding="utf-8") == "a\n"
    assert not (root / ".asc-os.lock").exists()


def test_hand_authored_file_is_not_overwritten(tmp_path: Path) -> None:
    destination = tmp_path / "report.md"
    destination.write_text("human\n", encoding="utf-8")
    plan = WritePlan(tmp_path, (), (PlannedWrite("report.md", "tool\n"),))
    with pytest.raises(WriteConflictError) as caught:
        apply_plan(plan)
    assert caught.value.detail.code == "hand_authored_conflict"
    assert destination.read_text(encoding="utf-8") == "human\n"


def test_owned_generated_file_requires_explicit_replacement(
    tmp_path: Path,
) -> None:
    digest = "a" * 64
    destination = tmp_path / "bundle.md"
    destination.write_text(
        generated_marker(digest) + "\nold\n", encoding="utf-8"
    )
    implicit = WritePlan(
        tmp_path,
        (),
        (
            PlannedWrite(
                "bundle.md", "new\n", generated=True, source_hash=digest
            ),
        ),
    )
    with pytest.raises(WriteConflictError):
        apply_plan(implicit)
    explicit = WritePlan(
        tmp_path,
        (),
        (
            PlannedWrite(
                "bundle.md",
                generated_marker(digest) + "\nnew\n",
                generated=True,
                source_hash=digest,
                allow_replace_owned=True,
            ),
        ),
    )
    apply_plan(explicit)
    assert destination.read_text(encoding="utf-8").endswith("new\n")


def test_existing_lock_blocks_second_writer(tmp_path: Path) -> None:
    with (
        ProjectLock(tmp_path),
        pytest.raises(WriteConflictError) as caught,
        ProjectLock(tmp_path),
    ):
        pytest.fail("the second lock must not be acquired")
    assert caught.value.detail.code == "project_locked"


def test_failed_atomic_replacement_preserves_previous_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = "b" * 64
    destination = tmp_path / "bundle.md"
    previous = generated_marker(digest) + "\ncomplete\n"
    destination.write_text(previous, encoding="utf-8")
    plan = WritePlan(
        tmp_path,
        (),
        (
            PlannedWrite(
                "bundle.md",
                generated_marker(digest) + "\nreplacement\n",
                generated=True,
                source_hash=digest,
                allow_replace_owned=True,
            ),
        ),
    )

    def fail_replace(_source: Path, _target: Path) -> Path:
        raise OSError("simulated replacement race")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(WriteConflictError, match="simulated replacement race"):
        apply_plan(plan)
    assert destination.read_text(encoding="utf-8") == previous
    assert not list(tmp_path.glob(".bundle.md.*.tmp"))


def test_output_symlink_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    plan = WritePlan(root, (), (PlannedWrite("link/result.txt", "x\n"),))
    with pytest.raises(UnsafePathError):
        apply_plan(plan)
    assert not (outside / "result.txt").exists()


def test_compare_before_replace_rejects_changed_previous_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "managed.yaml"
    destination.write_text("state: changed\n", encoding="utf-8")
    plan = WritePlan(
        tmp_path,
        (),
        (
            PlannedWrite(
                "managed.yaml",
                "state: finished\n",
                expected_previous_sha256="0" * 64,
            ),
        ),
    )
    with pytest.raises(WriteConflictError) as caught:
        apply_plan(plan)
    assert caught.value.detail.code == "hand_authored_conflict"
    assert destination.read_text(encoding="utf-8") == "state: changed\n"
