"""Integration tests for lifecycle transitions and immutable run records."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from asc_os.errors import LifecycleError, UnsafePathError
from asc_os.lifecycle import (
    Phase,
    finish_run,
    lifecycle_state,
    run_status,
    start_run,
)
from asc_os.scaffold import init_project

_START = datetime(2026, 8, 29, 0, 0, tzinfo=UTC)


def test_start_freezes_inputs_and_finish_is_immutable(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    started = start_run(root, "explore", started_at=_START)
    manifest = run_status(root, started.run_id)
    assert started.run_id == "RUN-20260829-000000"
    assert manifest.metadata.status == "active"
    assert "research/project.yaml" in manifest.spec["input_hashes"]
    assert manifest.spec["git"]["repository"] == "local/project"
    assert lifecycle_state(root).active_run == started.run_id
    finished = finish_run(
        root,
        started.run_id,
        0,
        finished_at=_START + timedelta(minutes=1),
    )
    completed = run_status(root, started.run_id)
    assert finished.status == "completed"
    assert completed.metadata.status == "completed"
    assert completed.spec["result"]["exit_code"] == 0
    with pytest.raises(LifecycleError) as caught:
        finish_run(root, started.run_id, 0, finished_at=_START)
    assert caught.value.detail.code == "run_already_finished"


def test_active_run_blocks_concurrent_start(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    first = start_run(root, "explore", started_at=_START)
    with pytest.raises(LifecycleError) as caught:
        start_run(root, "plan", started_at=_START + timedelta(seconds=1))
    assert caught.value.detail.code == "active_run_exists"
    assert lifecycle_state(root).active_run == first.run_id


@pytest.mark.parametrize(
    "phase",
    ["cover", "plan", "execute", "verify", "glue", "project"],
)
def test_initial_invalid_transitions_are_rejected(
    tmp_path: Path,
    phase: str,
) -> None:
    root = tmp_path / phase
    init_project(root)
    with pytest.raises(LifecycleError) as caught:
        start_run(root, cast(Phase, phase), started_at=_START)
    assert caught.value.detail.code == "invalid_lifecycle_transition"


def test_complete_lifecycle_sequence(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    phases: tuple[Phase, ...] = (
        "explore",
        "cover",
        "plan",
        "execute",
        "verify",
        "glue",
        "project",
    )
    for index, phase in enumerate(phases):
        timestamp = _START + timedelta(minutes=index * 2)
        operation = start_run(root, phase, started_at=timestamp)
        finish_run(
            root,
            operation.run_id,
            0,
            finished_at=timestamp + timedelta(minutes=1),
        )
    state = lifecycle_state(root)
    assert state.last_completed_phase == "project"
    assert state.active_run is None
    assert state.allowed_next == ("project",)


def test_dry_run_start_and_finish_do_not_mutate(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    preview = start_run(root, "explore", started_at=_START, dry_run=True)
    assert preview.plan.writes
    assert not (root / "research" / "runs" / preview.run_id).exists()
    started = start_run(root, "explore", started_at=_START)
    finish_preview = finish_run(
        root,
        started.run_id,
        0,
        finished_at=_START + timedelta(minutes=1),
        dry_run=True,
    )
    assert finish_preview.status == "completed"
    assert run_status(root, started.run_id).metadata.status == "active"


def test_same_timestamp_allocates_stable_sequence(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    first = start_run(root, "explore", started_at=_START)
    finish_run(root, first.run_id, 0, finished_at=_START)
    second = start_run(root, "plan", started_at=_START)
    assert second.run_id == "RUN-20260829-000000-002"


def test_finish_rejects_unsafe_or_missing_output(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    started = start_run(root, "explore", started_at=_START)
    with pytest.raises(UnsafePathError):
        finish_run(
            root,
            started.run_id,
            0,
            outputs=("../outside",),
            finished_at=_START,
        )


def test_failed_run_records_failure_without_advancing_phase(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    init_project(root)
    started = start_run(root, "explore", started_at=_START)
    finish_run(root, started.run_id, 7, finished_at=_START)
    manifest = run_status(root, started.run_id)
    assert manifest.metadata.status == "failed"
    assert manifest.spec["result"]["exit_code"] == 7
    assert lifecycle_state(root).allowed_next == ("explore",)
