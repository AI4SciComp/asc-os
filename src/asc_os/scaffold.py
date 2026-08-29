"""Non-overwriting project initialization and manifest scaffolding."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from asc_os.errors import ErrorDetail, ExitCode, WriteConflictError
from asc_os.storage import PlannedWrite, WritePlan, apply_plan

_DIRECTORIES = (
    ".ai/cache",
    ".ai/generated/claude",
    ".ai/generated/codex",
    ".ai/generated/common",
    "research/artifacts",
    "research/claims",
    "research/contexts/root",
    "research/covers",
    "research/decisions",
    "research/evidence",
    "research/log",
    "research/overlaps",
    "research/runs",
    "research/skills",
)

type _Builder = Callable[
    [str, str, dict[str, str]],
    tuple[dict[str, Any], str],
]


def init_plan(path: str | Path, *, adopt: bool = False) -> WritePlan:
    """Plan a safe research-layer initialization.

    Args:
        path: New or existing project directory.
        adopt: Permit adding only missing paths to a nonempty directory.

    Returns:
        A complete dry-run-capable write plan.

    Raises:
        WriteConflictError: If nonempty existing content is not adopted.

    """
    root = Path(path).expanduser().absolute()
    if (
        root.exists()
        and root.is_dir()
        and not root.is_symlink()
        and any(root.iterdir())
        and not adopt
    ):
        raise WriteConflictError(
            ErrorDetail(
                code="adopt_required",
                message="The target directory is not empty.",
                path=os.fspath(root),
                hint="Use --adopt to create only missing research-layer files.",
            ),
            ExitCode.WRITE_CONFLICT,
        )
    desired = _initial_files()
    writes: list[PlannedWrite] = []
    skipped: list[str] = []
    for relative, content in sorted(desired.items()):
        destination = root / relative
        if (
            destination.exists()
            and not destination.is_dir()
            and not (destination.is_symlink())
        ):
            skipped.append(relative)
        else:
            writes.append(PlannedWrite(relative, content))
    directories = tuple(
        item
        for item in _DIRECTORIES
        if not (root / item).is_dir() or (root / item).is_symlink()
    )
    return WritePlan(root, directories, tuple(writes), tuple(skipped))


def init_project(
    path: str | Path,
    *,
    adopt: bool = False,
    dry_run: bool = False,
) -> WritePlan:
    """Initialize a research layer without overwriting existing files."""
    return apply_plan(init_plan(path, adopt=adopt), dry_run=dry_run)


def scaffold_plan(
    project_root: Path,
    kind: str,
    record_id: str,
    title: str,
    **values: str,
) -> WritePlan:
    """Plan one canonical manifest scaffold."""
    builders: dict[str, _Builder] = {
        "context": _context_document,
        "cover": _cover_document,
        "overlap": _overlap_document,
        "claim": _claim_document,
        "decision": _decision_document,
        "evidence": _evidence_document,
        "artifact": _artifact_document,
    }
    try:
        document, relative = builders[kind](record_id, title, values)
    except KeyError as error:
        raise ValueError(f"Unsupported scaffold kind: {kind}") from error
    return WritePlan(
        root=project_root,
        directories=(str(Path(relative).parent),),
        writes=(PlannedWrite(relative, _dump(document)),),
    )


def scaffold_manifest(
    project_root: Path,
    kind: str,
    record_id: str,
    title: str,
    *,
    dry_run: bool = False,
    **values: str,
) -> WritePlan:
    """Create one missing manifest or return its dry-run plan."""
    plan = scaffold_plan(project_root, kind, record_id, title, **values)
    return apply_plan(plan, dry_run=dry_run)


def _initial_files() -> dict[str, str]:
    files: dict[str, str] = {
        "RESEARCH.md": (
            "# Research state\n\nCanonical authored state lives under "
            "`research/`; generated bundles are not authoritative.\n"
        ),
        "AGENTS.md": (
            "# Repository instructions\n\nRead `RESEARCH.md`, validate with "
            "`asc-os validate`, and use the generated context bundle for "
            "the assigned context. Never overwrite authored research state.\n"
        ),
        ".ai/cache/.gitignore": "*\n!.gitignore\n",
        "research/notation.yaml": "symbols: {}\n",
        "research/assumptions.yaml": "assumptions: []\n",
        "research/contexts/root/README.md": "# Root context\n",
        "research/contexts/root/state.yaml": "state: draft\n",
        "research/contexts/root/sources.yaml": "sources: []\n",
        "research/contexts/root/open_questions.yaml": "open_questions: []\n",
    }
    files["research/project.yaml"] = _dump(_project_document())
    files["research/contexts/root/context.yaml"] = _dump(
        _context_document("CTX-ROOT", "Root research context", {})[0]
    )
    return files


def _metadata(record_id: str, title: str) -> dict[str, Any]:
    return {"id": record_id, "title": title, "status": "draft", "labels": []}


def _envelope(
    kind: str, record_id: str, title: str, spec: Any
) -> dict[str, Any]:
    return {
        "api_version": "ai4scicomp.research/v1",
        "kind": kind,
        "metadata": _metadata(record_id, title),
        "spec": spec,
    }


def _project_document() -> dict[str, Any]:
    document = _envelope(
        "ResearchProject",
        "PRJ-0001",
        "Research project",
        {
            "repository": "local/project",
            "root_context": "CTX-ROOT",
            "notation": "research/notation.yaml",
            "assumptions": "research/assumptions.yaml",
            "required_covers": [],
            "artifact_targets": [],
            "policies": {
                "verified_claim_requires_evidence": True,
                "generated_outputs_are_authoritative": False,
            },
        },
    )
    document["metadata"]["status"] = "active"
    return document


def _context_document(
    record_id: str, title: str, values: dict[str, str]
) -> tuple[dict[str, Any], str]:
    slug = record_id.removeprefix("CTX-").lower().replace("_", "-")
    document = _envelope(
        "ResearchContext",
        record_id,
        title,
        {
            "parent": values.get("parent"),
            "question": values.get("question", "Define the bounded question."),
            "inputs": {"contexts": [], "files": []},
            "outputs": [],
            "acceptance": [],
            "excluded_scope": [],
        },
    )
    return document, f"research/contexts/{slug}/context.yaml"


def _cover_document(
    record_id: str, title: str, values: dict[str, str]
) -> tuple[dict[str, Any], str]:
    spec: dict[str, Any] = {
        "target": values.get("target", "CTX-ROOT"),
        "members": [],
        "requirements": {"deliverable": []},
        "required_overlaps": [],
    }
    return _envelope("ResearchCover", record_id, title, spec), (
        f"research/covers/{record_id}.yaml"
    )


def _overlap_document(
    record_id: str, title: str, values: dict[str, str]
) -> tuple[dict[str, Any], str]:
    spec: dict[str, Any] = {
        "left": values.get("left", "CTX-LEFT"),
        "right": values.get("right", "CTX-RIGHT"),
        "checks": [
            {
                "id": "declared-file",
                "type": "file_exists",
                "left": {"file": "research/notation.yaml"},
            }
        ],
        "failure_policy": "block_gluing",
    }
    return _envelope("ResearchOverlap", record_id, title, spec), (
        f"research/overlaps/{record_id}.yaml"
    )


def _claim_document(
    record_id: str, title: str, values: dict[str, str]
) -> tuple[dict[str, Any], str]:
    spec: dict[str, Any] = {
        "context": values.get("context", "CTX-ROOT"),
        "statement": values.get("statement", "State the bounded claim."),
        "assumptions": [],
        "depends_on": [],
        "evidence": [],
        "projections": {},
    }
    return _envelope("ResearchClaim", record_id, title, spec), (
        f"research/claims/{record_id}.yaml"
    )


def _decision_document(
    record_id: str, title: str, values: dict[str, str]
) -> tuple[dict[str, Any], str]:
    spec: dict[str, Any] = {
        "decision": values.get("decision", "Record the decision."),
        "rationale": ["Record the rationale."],
        "evidence": [],
        "supersedes": [],
        "affected_contexts": [],
    }
    return _envelope("ResearchDecision", record_id, title, spec), (
        f"research/decisions/{record_id}.yaml"
    )


def _evidence_document(
    record_id: str, title: str, values: dict[str, str]
) -> tuple[dict[str, Any], str]:
    spec: dict[str, Any] = {
        "evidence_type": values.get("evidence_type", "unit_test"),
        "produced_by_run": None,
        "sources": [
            {
                "uri": "file:results/evidence.json",
                "sha256": "0" * 64,
                "media_type": "application/json",
            }
        ],
        "supports": [],
        "limitations": ["Scaffold placeholder; replace before verification."],
    }
    return _envelope("ResearchEvidence", record_id, title, spec), (
        f"research/evidence/{record_id}/manifest.yaml"
    )


def _artifact_document(
    record_id: str, title: str, values: dict[str, str]
) -> tuple[dict[str, Any], str]:
    artifact_type = values.get("artifact_type", "report")
    spec: dict[str, Any] = {
        "artifact_type": artifact_type,
        "contexts": [],
        "claims": [],
        "required_evidence_classes": [],
        "output_contract": {
            "format": "manifest_only",
            "path": f"build/artifacts/{artifact_type}-manifest.json",
        },
    }
    return _envelope("ResearchArtifact", record_id, title, spec), (
        f"research/artifacts/{record_id}.yaml"
    )


def _dump(document: dict[str, Any]) -> str:
    return yaml.safe_dump(
        document,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
