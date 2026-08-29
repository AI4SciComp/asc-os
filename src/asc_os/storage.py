"""Dry-run planning, project locks, and atomic confined writes."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from asc_os.canonical import file_hash
from asc_os.errors import ErrorDetail, ExitCode, WriteConflictError
from asc_os.paths import confined_path


@dataclass(frozen=True, slots=True)
class PlannedWrite:
    """One deterministic file-write operation."""

    path: str
    content: str
    generated: bool = False
    source_hash: str | None = None
    allow_replace_owned: bool = False
    expected_previous_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class WritePlan:
    """Complete filesystem plan for one project operation."""

    root: Path
    directories: tuple[str, ...]
    writes: tuple[PlannedWrite, ...]
    skipped: tuple[str, ...] = ()

    @property
    def is_noop(self) -> bool:
        """Whether the plan would make no filesystem change."""
        return not self.directories and not self.writes

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic, content-free plan summary."""
        return {
            "root": os.fspath(self.root),
            "directories": list(self.directories),
            "writes": [
                {
                    "path": item.path,
                    "bytes": len(item.content.encode("utf-8")),
                    "generated": item.generated,
                    "source_hash": item.source_hash,
                    "allow_replace_owned": item.allow_replace_owned,
                    "expected_previous_sha256": item.expected_previous_sha256,
                }
                for item in self.writes
            ],
            "skipped": list(self.skipped),
            "noop": self.is_noop,
        }


class ProjectLock(AbstractContextManager["ProjectLock"]):
    """Exclusive project-local lock backed by atomic file creation."""

    def __init__(self, root: Path) -> None:
        """Initialize a lock for ``root`` without acquiring it."""
        self.path = root / ".asc-os.lock"
        self._descriptor: int | None = None

    def __enter__(self) -> ProjectLock:
        """Acquire the exclusive project-local lock."""
        descriptor: int | None = None
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
            os.fsync(descriptor)
            self._descriptor = descriptor
        except FileExistsError as error:
            raise _conflict(
                "project_locked",
                "Another ASC OS write holds the project lock.",
                self.path,
                "Wait for the other operation or inspect the stale lock.",
            ) from error
        except OSError:
            if descriptor is not None:
                os.close(descriptor)
                self.path.unlink(missing_ok=True)
            raise
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Release this instance's lock after the protected operation."""
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None
            self.path.unlink(missing_ok=True)


def apply_plan(plan: WritePlan, *, dry_run: bool = False) -> WritePlan:
    """Validate and optionally apply a complete write plan.

    Args:
        plan: Planned directories and exact UTF-8 file contents.
        dry_run: Validate and return without mutation.

    Returns:
        The validated plan.

    Raises:
        WriteConflictError: If a destination conflicts or a lock is held.

    """
    root = plan.root.absolute()
    _validate_root(root)
    preview = _effective_plan(plan)
    if dry_run or preview.is_noop:
        return preview
    root.mkdir(parents=True, exist_ok=True)
    with ProjectLock(root):
        effective = _effective_plan(plan)
        for directory in effective.directories:
            confined_path(root, directory, reject_symlinks=True).mkdir(
                parents=True,
                exist_ok=True,
            )
        for item in effective.writes:
            destination = confined_path(
                root,
                item.path,
                reject_symlinks=True,
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(destination, item.content.encode("utf-8"))
    return effective


def generated_marker(source_hash: str) -> str:
    """Return the standard Markdown generated-file ownership marker."""
    return f"<!-- generated-by: asc-os; source-sha256: {source_hash} -->"


def generated_json_metadata(source_hash: str) -> dict[str, str]:
    """Return standard JSON generated-file ownership metadata."""
    return {
        "generator": "asc-os",
        "generator_version": "0.1.0.dev0",
        "source_sha256": source_hash,
    }


def _effective_plan(plan: WritePlan) -> WritePlan:
    root = plan.root.absolute()
    directories: list[str] = []
    writes: list[PlannedWrite] = []
    skipped = list(plan.skipped)
    for directory in sorted(set(plan.directories)):
        destination = confined_path(root, directory, reject_symlinks=True)
        if destination.exists():
            if not destination.is_dir():
                raise _conflict(
                    "directory_conflict",
                    "A planned directory is occupied by a file.",
                    destination,
                    "Choose an unoccupied path.",
                )
            skipped.append(directory)
        else:
            directories.append(directory)
    seen: set[str] = set()
    for item in sorted(plan.writes, key=lambda entry: entry.path):
        if item.path in seen:
            raise _conflict(
                "duplicate_write",
                "The write plan contains the same path twice.",
                root / item.path,
                "Generate a plan with unique destinations.",
            )
        seen.add(item.path)
        destination = confined_path(root, item.path, reject_symlinks=True)
        encoded = item.content.encode("utf-8")
        if destination.exists():
            if destination.is_dir():
                raise _conflict(
                    "file_conflict",
                    "A planned file is occupied by a directory.",
                    destination,
                    "Choose an unoccupied path.",
                )
            if destination.read_bytes() == encoded:
                skipped.append(item.path)
                continue
            expected_matches = (
                item.expected_previous_sha256 is not None
                and file_hash(destination) == item.expected_previous_sha256
            )
            if not expected_matches and (
                not item.generated
                or not item.allow_replace_owned
                or not _owned_generated(destination)
            ):
                raise _conflict(
                    "hand_authored_conflict",
                    "Refusing to overwrite a hand-authored file.",
                    destination,
                    "Move the file or choose a new output path.",
                )
        writes.append(item)
    return WritePlan(
        root=root,
        directories=tuple(directories),
        writes=tuple(writes),
        skipped=tuple(sorted(set(skipped))),
    )


def _owned_generated(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if text.startswith("<!-- generated-by: asc-os; source-sha256: "):
        return True
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, dict):
        return False
    document = cast(dict[object, object], parsed)
    metadata = document.get("_asc_os")
    if not isinstance(metadata, dict):
        return False
    owned = cast(dict[object, object], metadata)
    return owned.get("generator") == "asc-os" and isinstance(
        owned.get("source_sha256"), str
    )


def _atomic_write(destination: Path, payload: bytes) -> None:
    temporary: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary = Path(raw_path)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
        temporary = None
        _sync_directory(destination.parent)
    except OSError as error:
        raise _conflict(
            "atomic_write_failed",
            str(error),
            destination,
            "Resolve the filesystem error; the previous file was preserved.",
        ) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _validate_root(root: Path) -> None:
    if root == Path(root.anchor) or (root.exists() and root.is_symlink()):
        raise _conflict(
            "unsafe_project_root",
            "Refusing a filesystem root or symlink as a project root.",
            root,
            "Choose a normal project directory.",
        )
    if root.exists() and not root.is_dir():
        raise _conflict(
            "project_root_conflict",
            "The project root is occupied by a file.",
            root,
            "Choose an unoccupied directory.",
        )


def _conflict(
    code: str,
    message: str,
    path: Path,
    hint: str,
) -> WriteConflictError:
    return WriteConflictError(
        ErrorDetail(
            code=code,
            message=message,
            path=os.fspath(path),
            hint=hint,
        ),
        ExitCode.WRITE_CONFLICT,
    )
