"""Command-line adapter for ASC OS services."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from asc_os.api import validate_project
from asc_os.canonical import canonical_data, canonical_json
from asc_os.context import Harness, OutputFormat, build_context
from asc_os.errors import AscOSError, ErrorDetail, ExitCode
from asc_os.lifecycle import Phase, finish_run, run_status, start_run
from asc_os.manifest import Manifest, load_project_state
from asc_os.paths import find_project_root
from asc_os.projection import (
    artifact_check,
    create_artifact_manifest,
    create_gluing_manifest,
    glue_check,
)
from asc_os.provenance import check_claim, inspect_evidence
from asc_os.scaffold import init_project, scaffold_manifest
from asc_os.skills import validate_skill
from asc_os.verification import check_cover, check_overlap
from asc_os.version import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the complete deterministic command parser."""
    parser = argparse.ArgumentParser(
        prog="asc-os",
        description="Local-first research state and compatibility tools.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="Inspect the local toolchain.")
    _add_json(doctor)

    initialize = commands.add_parser("init", help="Initialize research state.")
    initialize.add_argument("path")
    initialize.add_argument("--adopt", action="store_true")
    initialize.add_argument("--dry-run", action="store_true")
    _add_json(initialize)

    validate = commands.add_parser("validate", help="Validate a project.")
    validate.add_argument("path", nargs="?", default=".")
    _add_json(validate)

    _build_scaffold_parser(commands)
    _build_context_parser(commands)
    _build_cover_parser(commands)
    _build_overlap_parser(commands)
    _build_claim_parser(commands)
    _build_decision_parser(commands)
    _build_evidence_parser(commands)
    _build_run_parser(commands)
    _build_glue_parser(commands)
    _build_artifact_parser(commands)
    _build_skill_parser(commands)
    _build_mcp_parser(commands)
    return parser


def _build_scaffold_parser(commands: Any) -> None:
    scaffold = commands.add_parser("scaffold", help="Scaffold one manifest.")
    kinds = scaffold.add_subparsers(dest="scaffold_kind", required=True)
    for kind in ("context", "cover", "claim", "decision"):
        item = kinds.add_parser(kind)
        item.add_argument("--id", required=True)
        item.add_argument("--title", required=True)
        item.add_argument("--dry-run", action="store_true")
        _add_json(item)
    overlap = kinds.add_parser("overlap")
    overlap.add_argument("--id", required=True)
    overlap.add_argument("--left", required=True)
    overlap.add_argument("--right", required=True)
    overlap.add_argument("--dry-run", action="store_true")
    _add_json(overlap)
    evidence = kinds.add_parser("evidence")
    evidence.add_argument("--id", required=True)
    evidence.add_argument("--type", dest="record_type", required=True)
    evidence.add_argument("--dry-run", action="store_true")
    _add_json(evidence)
    artifact = kinds.add_parser("artifact")
    artifact.add_argument("--id", required=True)
    artifact.add_argument("--type", dest="record_type", required=True)
    artifact.add_argument("--dry-run", action="store_true")
    _add_json(artifact)


def _build_context_parser(commands: Any) -> None:
    context = commands.add_parser("context", help="Inspect or build contexts.")
    actions = context.add_subparsers(dest="context_command", required=True)
    listing = actions.add_parser("list")
    _add_json(listing)
    show = actions.add_parser("show")
    show.add_argument("context_id")
    _add_json(show)
    build = actions.add_parser("build")
    build.add_argument("context_id")
    build.add_argument(
        "--harness", choices=("common", "codex", "claude"), required=True
    )
    build.add_argument("--max-bytes", type=int, default=1024 * 1024)
    build.add_argument("--include-evidence-summary", action="store_true")
    build.add_argument("--include-source-excerpts", action="store_true")
    build.add_argument(
        "--format",
        dest="output_format",
        choices=("json", "markdown"),
        default="markdown",
    )
    build.add_argument("--install-entrypoint", action="store_true")
    build.add_argument("--force", action="store_true")
    build.add_argument("--dry-run", action="store_true")
    _add_json(build)


def _build_cover_parser(commands: Any) -> None:
    cover = commands.add_parser("cover", help="Inspect declared covers.")
    actions = cover.add_subparsers(dest="cover_command", required=True)
    listing = actions.add_parser("list")
    _add_json(listing)
    check = actions.add_parser("check")
    check.add_argument("cover_id", nargs="?")
    _add_json(check)


def _build_overlap_parser(commands: Any) -> None:
    overlap = commands.add_parser("overlap", help="Check compatibility.")
    actions = overlap.add_subparsers(dest="overlap_command", required=True)
    listing = actions.add_parser("list")
    _add_json(listing)
    check = actions.add_parser("check")
    check.add_argument("overlap_id", nargs="?")
    _add_json(check)


def _build_claim_parser(commands: Any) -> None:
    claim = commands.add_parser("claim", help="Inspect research claims.")
    actions = claim.add_subparsers(dest="claim_command", required=True)
    listing = actions.add_parser("list")
    listing.add_argument("--status")
    _add_json(listing)
    show = actions.add_parser("show")
    show.add_argument("claim_id")
    _add_json(show)
    check = actions.add_parser("check")
    check.add_argument("claim_id", nargs="?")
    _add_json(check)


def _build_decision_parser(commands: Any) -> None:
    decision = commands.add_parser("decision", help="Inspect decisions.")
    actions = decision.add_subparsers(dest="decision_command", required=True)
    listing = actions.add_parser("list")
    listing.add_argument("--status")
    _add_json(listing)
    show = actions.add_parser("show")
    show.add_argument("decision_id")
    _add_json(show)


def _build_evidence_parser(commands: Any) -> None:
    evidence = commands.add_parser("evidence", help="Inspect evidence.")
    actions = evidence.add_subparsers(dest="evidence_command", required=True)
    show = actions.add_parser("show")
    show.add_argument("evidence_id")
    _add_json(show)
    verify = actions.add_parser("verify")
    verify.add_argument("evidence_id")
    _add_json(verify)


def _build_run_parser(commands: Any) -> None:
    run = commands.add_parser("run", help="Record lifecycle runs.")
    actions = run.add_subparsers(dest="run_command", required=True)
    start = actions.add_parser("start")
    start.add_argument(
        "--phase",
        choices=(
            "explore",
            "cover",
            "plan",
            "execute",
            "verify",
            "glue",
            "project",
        ),
        required=True,
    )
    start.add_argument("--context", dest="context_id")
    start.add_argument("--dry-run", action="store_true")
    _add_json(start)
    status = actions.add_parser("status")
    status.add_argument("run_id")
    _add_json(status)
    finish = actions.add_parser("finish")
    finish.add_argument("run_id")
    finish.add_argument("--exit-code", type=int, required=True)
    finish.add_argument("--output", action="append", default=[])
    finish.add_argument("--dry-run", action="store_true")
    _add_json(finish)


def _build_glue_parser(commands: Any) -> None:
    glue = commands.add_parser("glue", help="Check or manifest gluing.")
    actions = glue.add_subparsers(dest="glue_command", required=True)
    check = actions.add_parser("check")
    check.add_argument("cover_id", nargs="?")
    _add_json(check)
    manifest = actions.add_parser("manifest")
    manifest.add_argument("cover_id")
    manifest.add_argument("--output", required=True)
    manifest.add_argument("--force", action="store_true")
    manifest.add_argument("--dry-run", action="store_true")
    _add_json(manifest)


def _build_artifact_parser(commands: Any) -> None:
    artifact = commands.add_parser("artifact", help="Project artifacts.")
    actions = artifact.add_subparsers(dest="artifact_command", required=True)
    check = actions.add_parser("check")
    check.add_argument("artifact_id")
    _add_json(check)
    manifest = actions.add_parser("manifest")
    manifest.add_argument("artifact_id")
    manifest.add_argument("--output", required=True)
    manifest.add_argument("--force", action="store_true")
    manifest.add_argument("--dry-run", action="store_true")
    _add_json(manifest)


def _build_skill_parser(commands: Any) -> None:
    skill = commands.add_parser("skill", help="Inspect descriptive skills.")
    actions = skill.add_subparsers(dest="skill_command", required=True)
    listing = actions.add_parser("list")
    _add_json(listing)
    validate = actions.add_parser("validate")
    validate.add_argument("skill_id")
    _add_json(validate)


def _build_mcp_parser(commands: Any) -> None:
    mcp = commands.add_parser("mcp", help="Serve local MCP over stdio.")
    actions = mcp.add_subparsers(dest="mcp_command", required=True)
    serve = actions.add_parser("serve")
    serve.add_argument("--transport", choices=("stdio",), required=True)
    serve.add_argument("--project", default=".")


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a stable exit code."""
    args = build_parser().parse_args(argv)
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "doctor": _handle_doctor,
        "init": _handle_init,
        "validate": _handle_validate,
        "scaffold": _handle_scaffold,
        "context": _handle_context,
        "cover": _handle_cover,
        "overlap": _handle_overlap,
        "claim": _handle_claim,
        "decision": _handle_decision,
        "evidence": _handle_evidence,
        "run": _handle_run,
        "glue": _handle_glue,
        "artifact": _handle_artifact,
        "skill": _handle_skill,
        "mcp": _handle_mcp,
    }
    try:
        return handlers[cast(str, args.command)](args)
    except AscOSError as error:
        _emit_error(error.detail, bool(getattr(args, "json", False)))
        return int(error.exit_code)
    except Exception as error:  # noqa: BLE001
        detail = ErrorDetail(
            code="internal_error",
            message=str(error),
            hint=(
                "Re-run with validated inputs and report reproducible failures."
            ),
        )
        _emit_error(detail, bool(getattr(args, "json", False)))
        return int(ExitCode.INTERNAL)


def _handle_doctor(args: argparse.Namespace) -> int:
    data = {
        "status": "ok",
        "asc_os": __version__,
        "python": sys.version.split()[0],
        "git": shutil.which("git"),
        "uv": shutil.which("uv"),
        "mcp_sdk": importlib.util.find_spec("mcp") is not None,
        "transport": "stdio-only",
    }
    _emit(data, args.json, "ASC OS doctor: ok (stdio-only MCP)")
    return 0


def _handle_init(args: argparse.Namespace) -> int:
    plan = init_project(args.path, adopt=args.adopt, dry_run=args.dry_run)
    _emit(plan.to_dict(), args.json, _plan_text(plan.to_dict()))
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    report = validate_project(args.path)
    text = (
        f"valid: {report.manifest_count} manifests in {report.project_root}"
        if report.valid
        else "\n".join(
            f"{item['code']}: {item['message']}" for item in report.errors
        )
    )
    _emit(report.to_dict(), args.json, text, error=not report.valid)
    return report.exit_code


def _handle_scaffold(args: argparse.Namespace) -> int:
    root = find_project_root()
    kind = cast(str, args.scaffold_kind)
    title = getattr(args, "title", None) or f"{args.id} {kind}"
    values: dict[str, str] = {}
    if kind == "overlap":
        values = {"left": args.left, "right": args.right}
    elif kind == "evidence":
        values = {"evidence_type": args.record_type}
    elif kind == "artifact":
        values = {"artifact_type": args.record_type}
    plan = scaffold_manifest(
        root,
        kind,
        args.id,
        title,
        dry_run=args.dry_run,
        **values,
    )
    _emit(plan.to_dict(), args.json, _plan_text(plan.to_dict()))
    return 0


def _handle_context(args: argparse.Namespace) -> int:
    state = load_project_state()
    if args.context_command == "list":
        return _emit_listing(args, state.by_kind("ResearchContext"))
    if args.context_command == "show":
        item = state.require(args.context_id, "ResearchContext")
        _emit(item.to_dict(), args.json, _manifest_text(item))
        return 0
    result = build_context(
        state.root,
        args.context_id,
        harness=cast(Harness, args.harness),
        max_bytes=args.max_bytes,
        include_evidence_summary=args.include_evidence_summary,
        include_source_excerpts=args.include_source_excerpts,
        output_format=cast(OutputFormat, args.output_format),
        install_entrypoint=args.install_entrypoint,
        force=args.force,
        dry_run=args.dry_run,
    )
    _emit(result.to_dict(), args.json, _plan_text(result.plan.to_dict()))
    return 0


def _handle_cover(args: argparse.Namespace) -> int:
    state = load_project_state()
    if args.cover_command == "list":
        return _emit_listing(args, state.by_kind("ResearchCover"))
    ids = _selected_ids(state, "ResearchCover", args.cover_id)
    reports = [check_cover(state.root, item).to_dict() for item in ids]
    return _emit_checks(args, reports, ExitCode.COMPATIBILITY_FAILED)


def _handle_overlap(args: argparse.Namespace) -> int:
    state = load_project_state()
    if args.overlap_command == "list":
        return _emit_listing(args, state.by_kind("ResearchOverlap"))
    ids = _selected_ids(state, "ResearchOverlap", args.overlap_id)
    reports = [check_overlap(state.root, item).to_dict() for item in ids]
    return _emit_checks(args, reports, ExitCode.COMPATIBILITY_FAILED)


def _handle_claim(args: argparse.Namespace) -> int:
    state = load_project_state()
    if args.claim_command == "list":
        items = state.by_kind("ResearchClaim")
        if args.status:
            items = tuple(
                item for item in items if item.metadata.status == args.status
            )
        return _emit_listing(args, items)
    if args.claim_command == "show":
        item = state.require(args.claim_id, "ResearchClaim")
        _emit(item.to_dict(), args.json, _manifest_text(item))
        return 0
    ids = _selected_ids(state, "ResearchClaim", args.claim_id)
    reports = [check_claim(state.root, item).to_dict() for item in ids]
    failed = [item for item in reports if not cast(bool, item["passed"])]
    exit_code = (
        ExitCode.STALE
        if any(cast(bool, item["stale"]) for item in failed)
        else ExitCode.EVIDENCE_POLICY
    )
    return _emit_checks(args, reports, exit_code)


def _handle_decision(args: argparse.Namespace) -> int:
    state = load_project_state()
    if args.decision_command == "show":
        item = state.require(args.decision_id, "ResearchDecision")
        _emit(item.to_dict(), args.json, _manifest_text(item))
        return 0
    items = state.by_kind("ResearchDecision")
    if args.status:
        items = tuple(
            item for item in items if item.metadata.status == args.status
        )
    return _emit_listing(args, items)


def _handle_evidence(args: argparse.Namespace) -> int:
    state = load_project_state()
    if args.evidence_command == "show":
        item = state.require(args.evidence_id, "ResearchEvidence")
        _emit(item.to_dict(), args.json, _manifest_text(item))
        return 0
    report = inspect_evidence(state.root, args.evidence_id)
    _emit(report.to_dict(), args.json, _report_text(report.to_dict()))
    return 0 if report.passed else int(ExitCode.EVIDENCE_POLICY)


def _handle_run(args: argparse.Namespace) -> int:
    if args.run_command == "start":
        operation = start_run(
            ".",
            cast(Phase, args.phase),
            context_id=args.context_id,
            dry_run=args.dry_run,
        )
        _emit(
            operation.to_dict(), args.json, _plan_text(operation.plan.to_dict())
        )
        return 0
    if args.run_command == "status":
        item = run_status(".", args.run_id)
        _emit(item.to_dict(), args.json, _manifest_text(item))
        return 0
    operation = finish_run(
        ".",
        args.run_id,
        args.exit_code,
        outputs=args.output,
        dry_run=args.dry_run,
    )
    _emit(operation.to_dict(), args.json, _plan_text(operation.plan.to_dict()))
    return 0


def _handle_glue(args: argparse.Namespace) -> int:
    state = load_project_state()
    if args.glue_command == "check":
        ids = _selected_ids(state, "ResearchCover", args.cover_id)
        reports = [glue_check(state.root, item).to_dict() for item in ids]
        return _emit_checks(args, reports, ExitCode.COMPATIBILITY_FAILED)
    operation = create_gluing_manifest(
        state.root,
        args.cover_id,
        args.output,
        dry_run=args.dry_run,
        force=args.force,
        allow_external_output=True,
    )
    _emit(operation.to_dict(), args.json, _plan_text(operation.plan.to_dict()))
    return 0


def _handle_artifact(args: argparse.Namespace) -> int:
    state = load_project_state()
    if args.artifact_command == "check":
        report = artifact_check(state.root, args.artifact_id)
        return _emit_checks(
            args, [report.to_dict()], ExitCode.COMPATIBILITY_FAILED
        )
    operation = create_artifact_manifest(
        state.root,
        args.artifact_id,
        args.output,
        dry_run=args.dry_run,
        force=args.force,
        allow_external_output=True,
    )
    _emit(operation.to_dict(), args.json, _plan_text(operation.plan.to_dict()))
    return 0


def _handle_skill(args: argparse.Namespace) -> int:
    state = load_project_state()
    if args.skill_command == "list":
        return _emit_listing(args, state.by_kind("ResearchSkill"))
    report = validate_skill(state.root, args.skill_id)
    _emit(report.to_dict(), args.json, _report_text(report.to_dict()))
    return 0 if report.passed else int(ExitCode.SCHEMA_INVALID)


def _handle_mcp(args: argparse.Namespace) -> int:
    from asc_os.mcp_server import serve_project  # noqa: PLC0415

    return serve_project(args.project, transport=args.transport)


def _selected_ids(
    state: Any,
    kind: str,
    selected: str | None,
) -> tuple[str, ...]:
    if selected is not None:
        state.require(selected, kind)
        return (selected,)
    return tuple(item.id for item in state.by_kind(kind))


def _emit_listing(args: argparse.Namespace, items: Sequence[Manifest]) -> int:
    data = [
        {
            "id": item.id,
            "title": item.metadata.title,
            "status": item.metadata.status,
        }
        for item in items
    ]
    text = "\n".join(
        f"{item['id']}\t{item['status']}\t{item['title']}" for item in data
    )
    _emit({"items": data}, args.json, text or "No records.")
    return 0


def _emit_checks(
    args: argparse.Namespace,
    reports: list[dict[str, object]],
    failure_code: ExitCode,
) -> int:
    passed = all(cast(bool, item["passed"]) for item in reports)
    data = {"passed": passed, "reports": reports}
    _emit(data, args.json, _report_text(data), error=not passed)
    return 0 if passed else int(failure_code)


def _emit(
    data: object,
    json_mode: bool,
    text: str,
    *,
    error: bool = False,
) -> None:
    if json_mode:
        print(canonical_json(data))
    else:
        print(text, file=sys.stderr if error else sys.stdout)


def _emit_error(detail: ErrorDetail, json_mode: bool) -> None:
    data = {"error": canonical_data(detail)}
    if json_mode:
        print(canonical_json(data))
    else:
        print(f"{detail.code}: {detail.message}", file=sys.stderr)
        if detail.hint:
            print(f"hint: {detail.hint}", file=sys.stderr)


def _manifest_text(item: Manifest) -> str:
    return json.dumps(
        canonical_data(item),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _plan_text(plan: dict[str, object]) -> str:
    action = "no changes" if plan["noop"] else "planned filesystem changes"
    return f"{action}: {plan['root']}"


def _report_text(report: Mapping[str, object]) -> str:
    return json.dumps(
        canonical_data(report),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
