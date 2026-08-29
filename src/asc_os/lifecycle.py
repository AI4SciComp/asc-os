"""Deterministic research lifecycle state and immutable run records."""

from __future__ import annotations

import platform
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from asc_os.canonical import file_hash
from asc_os.context import git_state
from asc_os.errors import ErrorDetail, ExitCode, LifecycleError
from asc_os.manifest import Manifest, ProjectState, load_project_state
from asc_os.paths import confined_path, relative_posix
from asc_os.storage import PlannedWrite, WritePlan, apply_plan
from asc_os.version import __version__

Phase = Literal[
    "explore", "cover", "plan", "execute", "verify", "glue", "project"
]
_PHASES = frozenset(
    {"explore", "cover", "plan", "execute", "verify", "glue", "project"}
)
_MAX_EXIT_CODE = 255
_ALLOWED_NEXT: Mapping[str | None, frozenset[str]] = {
    None: frozenset({"explore"}),
    "explore": frozenset({"cover", "plan"}),
    "cover": frozenset({"plan", "execute"}),
    "plan": frozenset({"execute"}),
    "execute": frozenset({"execute", "verify"}),
    "verify": frozenset({"execute", "verify", "glue"}),
    "glue": frozenset({"project"}),
    "project": frozenset({"project"}),
}


@dataclass(frozen=True, slots=True)
class LifecycleState:
    """Current project lifecycle position."""

    last_completed_phase: str | None
    active_run: str | None
    allowed_next: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return stable JSON-compatible state."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RunOperation:
    """Run record plus its exact write plan."""

    run_id: str
    phase: str
    status: str
    plan: WritePlan

    def to_dict(self) -> dict[str, object]:
        """Return stable JSON-compatible operation data."""
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "status": self.status,
            "plan": self.plan.to_dict(),
        }


def lifecycle_state(project_path: str | Path) -> LifecycleState:
    """Return the current lifecycle position without mutation."""
    state = load_project_state(project_path)
    return _lifecycle_state(state)


def start_run(
    project_path: str | Path,
    phase: Phase,
    *,
    context_id: str | None = None,
    started_at: datetime | None = None,
    dry_run: bool = False,
) -> RunOperation:
    """Freeze inputs and start one valid lifecycle run."""
    state = load_project_state(project_path)
    current = _lifecycle_state(state)
    if current.active_run is not None:
        raise _lifecycle_error(
            "active_run_exists",
            f"Run {current.active_run!r} is still active.",
            "Finish the active run before starting another.",
        )
    if phase not in _PHASES or phase not in current.allowed_next:
        raise _lifecycle_error(
            "invalid_lifecycle_transition",
            f"Cannot transition from {current.last_completed_phase!r} to "
            f"{phase!r}.",
            "Allowed next phases: " + ", ".join(current.allowed_next),
        )
    if context_id is not None:
        state.require(context_id, "ResearchContext")
    timestamp = _normalize_time(started_at or _utc_now())
    run_id = _new_run_id(state.root, timestamp)
    git = git_state(state.root)
    document: dict[str, Any] = {
        "api_version": "ai4scicomp.research/v1",
        "kind": "ResearchRun",
        "metadata": {
            "id": run_id,
            "title": f"{phase.capitalize()} research run",
            "status": "active",
            "labels": [phase],
        },
        "spec": {
            "phase": phase,
            "context": context_id,
            "input_hashes": _frozen_inputs(state),
            "tool_versions": {
                "asc-os": __version__,
                "python": platform.python_version(),
            },
            "git": {
                "repository": state.project.spec["repository"],
                "commit": git.commit,
                "dirty": git.dirty,
            },
            "started_at": _format_time(timestamp),
        },
    }
    relative = f"research/runs/{run_id}/run.yaml"
    plan = WritePlan(
        state.root,
        (f"research/runs/{run_id}/events",),
        (PlannedWrite(relative, _dump(document)),),
    )
    effective = apply_plan(plan, dry_run=dry_run)
    return RunOperation(run_id, phase, "active", effective)


def run_status(
    project_path: str | Path,
    run_id: str,
) -> Manifest:
    """Return one validated immutable run record."""
    state = load_project_state(project_path)
    return state.require(run_id, "ResearchRun")


def finish_run(
    project_path: str | Path,
    run_id: str,
    exit_code: int,
    *,
    outputs: Iterable[str] = (),
    finished_at: datetime | None = None,
    dry_run: bool = False,
) -> RunOperation:
    """Finish exactly one active run using compare-before-replace storage."""
    if not 0 <= exit_code <= _MAX_EXIT_CODE:
        raise _lifecycle_error(
            "invalid_run_exit_code",
            "Run exit code must be between 0 and 255.",
            "Choose a conventional process exit code.",
        )
    state = load_project_state(project_path)
    run = state.require(run_id, "ResearchRun")
    if run.metadata.status != "active" or "result" in run.spec:
        raise _lifecycle_error(
            "run_already_finished",
            f"Run {run_id!r} is not active.",
            "Run records are immutable after finish.",
        )
    output_paths = tuple(sorted(set(outputs)))
    for output in output_paths:
        confined_path(state.root, output, must_exist=True)
    timestamp = _normalize_time(finished_at or _utc_now())
    started = datetime.fromisoformat(
        cast(str, run.spec["started_at"]).replace("Z", "+00:00")
    )
    if timestamp < started:
        raise _lifecycle_error(
            "finish_precedes_start",
            "Run finish time precedes its start time.",
            "Use a finish time at or after started_at.",
        )
    document = run.to_dict()
    metadata = cast(dict[str, Any], document["metadata"])
    metadata["status"] = "completed" if exit_code == 0 else "failed"
    spec = cast(dict[str, Any], document["spec"])
    spec["finished_at"] = _format_time(timestamp)
    spec["result"] = {
        "exit_code": exit_code,
        "outputs": list(output_paths),
    }
    relative = relative_posix(state.root, run.path)
    plan = WritePlan(
        state.root,
        (),
        (
            PlannedWrite(
                relative,
                _dump(document),
                expected_previous_sha256=file_hash(run.path),
            ),
        ),
    )
    effective = apply_plan(plan, dry_run=dry_run)
    return RunOperation(
        run_id,
        cast(str, run.spec["phase"]),
        cast(str, metadata["status"]),
        effective,
    )


def _lifecycle_state(state: ProjectState) -> LifecycleState:
    runs = state.by_kind("ResearchRun")
    active = tuple(item for item in runs if item.metadata.status == "active")
    if len(active) > 1:
        raise _lifecycle_error(
            "multiple_active_runs",
            "More than one active run exists.",
            "Finish or correct conflicting run records manually.",
        )
    completed = tuple(
        item for item in runs if item.metadata.status == "completed"
    )
    last = max(
        completed,
        key=lambda item: (
            cast(str, item.spec.get("finished_at", "")),
            item.id,
        ),
        default=None,
    )
    last_phase = cast(str, last.spec["phase"]) if last is not None else None
    return LifecycleState(
        last_phase,
        active[0].id if active else None,
        tuple(sorted(_ALLOWED_NEXT[last_phase])),
    )


def _frozen_inputs(state: ProjectState) -> dict[str, str]:
    paths = {
        *(item.path for item in state.manifests),
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
    }
    return {
        relative_posix(state.root, path): file_hash(path)
        for path in sorted(paths)
    }


def _new_run_id(root: Path, timestamp: datetime) -> str:
    stem = f"RUN-{timestamp:%Y%m%d}-{timestamp:%H%M%S}"
    candidate = stem
    sequence = 2
    while (root / "research" / "runs" / candidate).exists():
        candidate = f"{stem}-{sequence:03d}"
        sequence += 1
    return candidate


def _normalize_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise _lifecycle_error(
            "naive_run_timestamp",
            "Run timestamps must include a timezone.",
            "Use an aware UTC timestamp.",
        )
    return value.astimezone(UTC).replace(microsecond=0)


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _dump(document: dict[str, Any]) -> str:
    return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)


def _lifecycle_error(code: str, message: str, hint: str) -> LifecycleError:
    return LifecycleError(
        ErrorDetail(code=code, message=message, hint=hint),
        ExitCode.COMPATIBILITY_FAILED,
    )
