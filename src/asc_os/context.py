"""Deterministic context restriction and harness bundle generation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from asc_os.canonical import (
    canonical_data,
    canonical_json,
    content_hash,
    file_hash,
)
from asc_os.errors import ContextBuildError, ErrorDetail, ExitCode
from asc_os.manifest import Manifest, ProjectState, load_project_state
from asc_os.paths import confined_path, relative_posix
from asc_os.storage import PlannedWrite, WritePlan, apply_plan, generated_marker

Harness = Literal["common", "codex", "claude"]
OutputFormat = Literal["json", "markdown"]
_HARNESSES = frozenset({"common", "codex", "claude"})
_FORMATS = frozenset({"json", "markdown"})


@dataclass(frozen=True, slots=True)
class GitState:
    """Stable Git provenance after excluding ASC OS derived output."""

    available: bool
    commit: str | None
    dirty: bool
    changes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextBuildResult:
    """Result of planning or writing one context bundle."""

    context_id: str
    harness: Harness
    source_hash: str
    plan: WritePlan

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic operation report."""
        return {
            "context_id": self.context_id,
            "harness": self.harness,
            "source_hash": self.source_hash,
            "plan": self.plan.to_dict(),
        }


def build_context_plan(  # noqa: PLR0913
    project_path: str | Path,
    context_id: str,
    *,
    harness: Harness = "common",
    max_bytes: int = 1024 * 1024,
    include_evidence_summary: bool = False,
    include_source_excerpts: bool = False,
    output_format: OutputFormat = "markdown",
    install_entrypoint: bool = False,
    force: bool = False,
) -> ContextBuildResult:
    """Build an exact, non-mutating plan for one restricted context bundle.

    Args:
        project_path: Project root or descendant.
        context_id: Stable ResearchContext identifier.
        harness: Harness-neutral common output or one presentation adapter.
        max_bytes: Maximum combined generated bundle size.
        include_evidence_summary: Include summaries of resolved evidence.
        include_source_excerpts: Include complete declared input text files.
        output_format: Presentation format used by adapter prompts.
        install_entrypoint: Create a missing root instruction entrypoint.
        force: Replace only verifiably ASC OS-owned generated output.

    Returns:
        The complete write plan and its material-input hash.

    Raises:
        ContextBuildError: If options or bounded inputs are invalid or too
            large.

    """
    _validate_options(harness, output_format, max_bytes, install_entrypoint)
    state = load_project_state(project_path)
    context = state.require(context_id, "ResearchContext")
    model = _context_model(
        state,
        context,
        include_evidence_summary=include_evidence_summary,
        include_source_excerpts=include_source_excerpts,
        max_bytes=max_bytes,
    )
    source_hash = content_hash(model)
    writes = _common_writes(context_id, model, source_hash, force)
    if harness != "common":
        writes.extend(
            _adapter_writes(
                context_id,
                harness,
                model,
                source_hash,
                output_format,
                force,
            )
        )
    if install_entrypoint:
        writes.extend(
            _entrypoint_write(state.root, context_id, harness, source_hash)
        )
    _enforce_size(writes, max_bytes)
    directories = tuple(
        sorted({str(Path(item.path).parent) for item in writes})
    )
    return ContextBuildResult(
        context_id=context_id,
        harness=harness,
        source_hash=source_hash,
        plan=WritePlan(state.root, directories, tuple(writes)),
    )


def build_context(  # noqa: PLR0913
    project_path: str | Path,
    context_id: str,
    *,
    harness: Harness = "common",
    max_bytes: int = 1024 * 1024,
    include_evidence_summary: bool = False,
    include_source_excerpts: bool = False,
    output_format: OutputFormat = "markdown",
    install_entrypoint: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> ContextBuildResult:
    """Plan and optionally write one deterministic context bundle."""
    result = build_context_plan(
        project_path,
        context_id,
        harness=harness,
        max_bytes=max_bytes,
        include_evidence_summary=include_evidence_summary,
        include_source_excerpts=include_source_excerpts,
        output_format=output_format,
        install_entrypoint=install_entrypoint,
        force=force,
    )
    effective = apply_plan(result.plan, dry_run=dry_run)
    return ContextBuildResult(
        context_id=result.context_id,
        harness=result.harness,
        source_hash=result.source_hash,
        plan=effective,
    )


def _validate_options(
    harness: str,
    output_format: str,
    max_bytes: int,
    install_entrypoint: bool,
) -> None:
    if harness not in _HARNESSES:
        raise _build_error(
            "unsupported_harness", f"Unsupported harness {harness!r}."
        )
    if output_format not in _FORMATS:
        raise _build_error(
            "unsupported_context_format",
            f"Unsupported context format {output_format!r}.",
        )
    if max_bytes <= 0:
        raise _build_error("invalid_max_bytes", "max_bytes must be positive.")
    if install_entrypoint and harness == "common":
        raise _build_error(
            "entrypoint_requires_harness",
            "Entrypoint installation requires the codex or claude harness.",
        )


def _context_model(
    state: ProjectState,
    context: Manifest,
    *,
    include_evidence_summary: bool,
    include_source_excerpts: bool,
    max_bytes: int,
) -> dict[str, Any]:
    upstream_ids = _string_list(_mapping(context.spec["inputs"])["contexts"])
    upstream = tuple(
        state.require(item, "ResearchContext") for item in upstream_ids
    )
    decisions = tuple(
        item
        for item in state.by_kind("ResearchDecision")
        if item.metadata.status == "active"
        and context.id in _string_list(item.spec["affected_contexts"])
    )
    claims = _required_claims(state, context)
    evidence_ids = sorted(
        {
            evidence_id
            for claim in claims
            for evidence_id in _string_list(claim.spec["evidence"])
        }
    )
    evidence = tuple(
        state.require(item, "ResearchEvidence") for item in evidence_ids
    )
    relevant_ids = {context.id, *upstream_ids}
    overlaps = tuple(
        item
        for item in state.by_kind("ResearchOverlap")
        if cast(str, item.spec["left"]) in relevant_ids
        or cast(str, item.spec["right"]) in relevant_ids
    )
    instructions = _applicable_instructions(state.root, context.path)
    notation_path = confined_path(
        state.root,
        cast(str, state.project.spec["notation"]),
        must_exist=True,
    )
    assumptions_path = confined_path(
        state.root,
        cast(str, state.project.spec["assumptions"]),
        must_exist=True,
    )
    source_paths = {
        state.project.path,
        context.path,
        notation_path,
        assumptions_path,
        *(item.path for item in upstream),
        *(item.path for item in decisions),
        *(item.path for item in claims),
        *(item.path for item in overlaps),
        *instructions,
    }
    if include_evidence_summary:
        source_paths.update(item.path for item in evidence)
    excerpts: dict[str, str] = {}
    if include_source_excerpts:
        for relative in _string_list(_mapping(context.spec["inputs"])["files"]):
            path = confined_path(state.root, relative, must_exist=True)
            source_paths.add(path)
            excerpts[relative] = _read_complete_text(path, max_bytes)
    ordered_sources = tuple(sorted(source_paths))
    hashes = {
        relative_posix(state.root, path): file_hash(path)
        for path in ordered_sources
    }
    instruction_content = {
        relative_posix(state.root, path): path.read_text(encoding="utf-8")
        for path in instructions
    }
    model: dict[str, Any] = {
        "api_version": "ai4scicomp.context/v1",
        "project": {
            "id": state.project.id,
            "title": state.project.metadata.title,
            "repository": state.project.spec["repository"],
            "policies": state.project.spec["policies"],
        },
        "context": context.to_dict(),
        "shared": {
            "notation": state.notation,
            "assumptions": state.assumptions,
        },
        "upstream_contexts": [_context_summary(item) for item in upstream],
        "decisions": [_decision_summary(item) for item in decisions],
        "claims": [_claim_summary(item) for item in claims],
        "evidence": (
            [_evidence_summary(item) for item in evidence]
            if include_evidence_summary
            else []
        ),
        "overlaps": [item.to_dict() for item in overlaps],
        "instructions": instruction_content,
        "source_excerpts": excerpts,
        "provenance": {
            "git": asdict(git_state(state.root)),
            "source_hashes": hashes,
        },
    }
    return model


def _required_claims(
    state: ProjectState, context: Manifest
) -> tuple[Manifest, ...]:
    selected = {
        item.id
        for item in state.by_kind("ResearchClaim")
        if cast(str, item.spec["context"]) == context.id
    }
    for output in cast(Iterable[Mapping[str, Any]], context.spec["outputs"]):
        if output.get("type") == "claim" and isinstance(output.get("id"), str):
            selected.add(cast(str, output["id"]))
    pending = list(selected)
    while pending:
        claim = state.require(pending.pop(), "ResearchClaim")
        for dependency in _string_list(claim.spec["depends_on"]):
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    return tuple(
        state.require(item, "ResearchClaim") for item in sorted(selected)
    )


def _applicable_instructions(
    root: Path, context_path: Path
) -> tuple[Path, ...]:
    relative_parent = context_path.parent.resolve().relative_to(root.resolve())
    directories = [root]
    current = root
    for part in relative_parent.parts:
        current /= part
        directories.append(current)
    found: set[Path] = set()
    for directory in directories:
        for name in ("AGENTS.md", "CLAUDE.md"):
            candidate = directory / name
            if candidate.is_file() and not _is_generated_instruction(candidate):
                relative = candidate.absolute().relative_to(root.absolute())
                found.add(confined_path(root, relative, must_exist=True))
    return tuple(sorted(found))


def _is_generated_instruction(path: Path) -> bool:
    try:
        prefix = path.read_text(encoding="utf-8")[:80]
    except (OSError, UnicodeDecodeError):
        return False
    return prefix.startswith("<!-- generated-by: asc-os; source-sha256: ")


def git_state(root: Path) -> GitState:
    """Return stable Git provenance, excluding ASC OS derived output."""
    executable = shutil.which("git")
    if executable is None:
        return GitState(False, None, False, ())
    commit = _run_git(executable, root, ("rev-parse", "HEAD"))
    if commit is None:
        return GitState(False, None, False, ())
    status = _run_git(
        executable,
        root,
        ("status", "--porcelain=v1", "--untracked-files=all"),
    )
    changes = tuple(
        sorted(
            line
            for line in (status or "").splitlines()
            if ".ai/generated/" not in line
            and ".ai/cache/" not in line
            and not line.endswith(" .asc-os.lock")
        )
    )
    return GitState(True, commit.strip(), bool(changes), changes)


def _run_git(
    executable: str, root: Path, arguments: tuple[str, ...]
) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603
            (executable, "-C", os.fspath(root), *arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _common_writes(
    context_id: str,
    model: dict[str, Any],
    source_hash: str,
    force: bool,
) -> list[PlannedWrite]:
    base = f".ai/generated/common/{context_id}"
    metadata = _ownership(source_hash)
    provenance = cast(dict[str, Any], model["provenance"])
    source_hashes = cast(dict[str, str], provenance["source_hashes"])
    sources = sorted(source_hashes)
    documents = {
        f"{base}/context.json": canonical_json(
            {"_asc_os": metadata, "context": model}
        )
        + "\n",
        f"{base}/context.md": generated_marker(source_hash)
        + "\n"
        + _render_markdown(model, source_hash),
        f"{base}/provenance.json": canonical_json(
            {
                "_asc_os": metadata,
                "provenance": provenance,
                "source_paths": sources,
            }
        )
        + "\n",
        f"{base}/source-hashes.json": canonical_json(
            {"_asc_os": metadata, "source_hashes": source_hashes}
        )
        + "\n",
    }
    return [
        PlannedWrite(
            path,
            content,
            generated=True,
            source_hash=source_hash,
            allow_replace_owned=force,
        )
        for path, content in sorted(documents.items())
    ]


def _adapter_writes(
    context_id: str,
    harness: Harness,
    model: dict[str, Any],
    source_hash: str,
    output_format: OutputFormat,
    force: bool,
) -> list[PlannedWrite]:
    base = f".ai/generated/{harness}/{context_id}"
    label = "AGENTS" if harness == "codex" else "CLAUDE"
    presentation = (
        canonical_json(model) + "\n"
        if output_format == "json"
        else _render_markdown(model, source_hash)
    )
    prompt = (
        generated_marker(source_hash)
        + "\n# Bounded research context\n\n"
        + "Use only the declared scope, inputs, tools, and acceptance "
        + "criteria. "
        + "Treat authored `research/` state as canonical.\n\n"
        + presentation
    )
    fragment = (
        generated_marker(source_hash)
        + f"\n# {label} context fragment\n\n"
        + f"Read `.ai/generated/common/{context_id}/context.md` before work. "
        + "Do not overwrite authored research state or act outside the "
        + "declared "
        + "context. Run `asc-os validate` before handoff.\n"
    )
    prompt_path = f"{base}/prompt.md"
    fragment_path = f"{base}/{label}.fragment.md"
    manifest_path = f"{base}/bundle-manifest.json"
    files = {
        prompt_path: prompt,
        fragment_path: fragment,
    }
    manifest = (
        canonical_json(
            {
                "_asc_os": _ownership(source_hash),
                "context_id": context_id,
                "harness": harness,
                "format": output_format,
                "source_sha256": source_hash,
                "files": {
                    path: _text_hash(content)
                    for path, content in sorted(files.items())
                },
            }
        )
        + "\n"
    )
    files[manifest_path] = manifest
    return [
        PlannedWrite(
            path,
            content,
            generated=True,
            source_hash=source_hash,
            allow_replace_owned=force,
        )
        for path, content in sorted(files.items())
    ]


def _entrypoint_write(
    root: Path,
    context_id: str,
    harness: Harness,
    source_hash: str,
) -> list[PlannedWrite]:
    name = "AGENTS.md" if harness == "codex" else "CLAUDE.md"
    if (root / name).exists():
        return []
    content = (
        generated_marker(source_hash)
        + "\n# Repository instructions\n\nRead `RESEARCH.md` and "
        + f"`.ai/generated/{harness}/{context_id}/prompt.md`. Preserve "
        + "authored "
        + "research state and run `asc-os validate` before handoff.\n"
    )
    return [PlannedWrite(name, content)]


def _render_markdown(model: dict[str, Any], source_hash: str) -> str:
    context = _mapping(model["context"])
    metadata = _mapping(context["metadata"])
    spec = _mapping(context["spec"])
    return (
        f"# Context {metadata['id']}: {metadata['title']}\n\n"
        + f"Source SHA-256: `{source_hash}`\n\n"
        + f"## Question\n\n{spec['question']}\n\n"
        + "## Restricted context model\n\n```json\n"
        + json.dumps(
            canonical_data(model),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n```\n"
    )


def _context_summary(item: Manifest) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.metadata.title,
        "status": item.metadata.status,
        "question": item.spec["question"],
        "outputs": item.spec["outputs"],
        "acceptance": item.spec["acceptance"],
    }


def _decision_summary(item: Manifest) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.metadata.title,
        "decision": item.spec["decision"],
        "rationale": item.spec["rationale"],
        "evidence": item.spec["evidence"],
    }


def _claim_summary(item: Manifest) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.metadata.title,
        "status": item.metadata.status,
        "statement": item.spec["statement"],
        "assumptions": item.spec["assumptions"],
        "depends_on": item.spec["depends_on"],
        "evidence": item.spec["evidence"],
    }


def _evidence_summary(item: Manifest) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.metadata.title,
        "status": item.metadata.status,
        "evidence_type": item.spec["evidence_type"],
        "sources": item.spec["sources"],
        "limitations": item.spec["limitations"],
    }


def _read_complete_text(path: Path, max_bytes: int) -> str:
    payload = path.read_bytes()
    if len(payload) > max_bytes:
        raise _build_error(
            "source_excerpt_too_large",
            f"Declared source {path} is {len(payload)} bytes, over "
            f"{max_bytes}.",
        )
    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise _build_error(
            "source_excerpt_not_utf8",
            f"Declared source {path} is not UTF-8 text.",
        ) from error


def _enforce_size(writes: list[PlannedWrite], max_bytes: int) -> None:
    sizes = sorted(
        (
            (len(item.content.encode("utf-8")), item.path)
            for item in writes
            if item.path.startswith(".ai/generated/")
        ),
        reverse=True,
    )
    total = sum(size for size, _path in sizes)
    if total <= max_bytes:
        return
    largest = ", ".join(f"{path}={size}" for size, path in sizes[:4])
    raise ContextBuildError(
        ErrorDetail(
            code="context_size_exceeded",
            message=f"Context bundle is {total} bytes; limit is {max_bytes}.",
            hint=(
                f"Largest sections: {largest}. Disable explicit evidence/"
                "source "
                "summaries or increase --max-bytes; content was not truncated."
            ),
        ),
        ExitCode.USAGE,
    )


def _ownership(source_hash: str) -> dict[str, str]:
    return {
        "generator": "asc-os",
        "generator_version": "0.1.0.dev0",
        "source_sha256": source_hash,
    }


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value)


def _string_list(value: object) -> tuple[str, ...]:
    return tuple(cast(Iterable[str], value))


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_error(code: str, message: str) -> ContextBuildError:
    return ContextBuildError(
        ErrorDetail(
            code=code,
            message=message,
            hint="Correct the context build request.",
        ),
        ExitCode.USAGE,
    )
