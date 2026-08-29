"""Official-SDK local stdio MCP adapter with a confined tool vocabulary."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from asc_os.api import validate_project as validate_project_service
from asc_os.canonical import canonical_json, content_hash
from asc_os.context import Harness, build_context, build_context_plan
from asc_os.errors import AscOSError
from asc_os.lifecycle import Phase, finish_run, start_run
from asc_os.manifest import ProjectState, SchemaCatalog, load_project_state
from asc_os.projection import (
    create_artifact_manifest as create_artifact_manifest_service,
)
from asc_os.projection import (
    create_gluing_manifest as create_gluing_manifest_service,
)
from asc_os.provenance import check_claim as check_claim_service
from asc_os.provenance import inspect_evidence as inspect_evidence_service
from asc_os.verification import check_cover as check_cover_service
from asc_os.verification import check_overlap as check_overlap_service
from asc_os.version import __version__

Transport = Literal["stdio"]
_PROMPT_MAX_BYTES = 1024 * 1024


def create_server(project_path: str | Path) -> MCPServer[Any]:
    """Create a server bound to one explicit, validated project root."""
    requested = Path(project_path).expanduser().absolute()
    state = load_project_state(requested)
    if requested.resolve() != state.root.resolve():
        raise ValueError("MCP startup requires the explicit project root")
    server: MCPServer[Any] = MCPServer(
        name="asc-os",
        title="ASC OS research state",
        description="Confined local research state and compatibility tools.",
        instructions=(
            "Use authored research state as canonical. No arbitrary execution, "
            "credential access, network fetch, or Git mutation is available."
        ),
        version=__version__,
        log_level="ERROR",
    )
    _register_resources(server, state)
    _register_prompts(server, state)
    _register_tools(server, state)
    return server


def serve_project(
    project_path: str | Path,
    *,
    transport: Transport = "stdio",
) -> int:
    """Serve one explicit project through the local stdio transport only."""
    if transport != "stdio":
        raise ValueError("ASC OS MCP supports only stdio transport")
    server = create_server(project_path)
    server.run(transport="stdio")
    return 0


def _register_resources(server: MCPServer[Any], state: ProjectState) -> None:
    @server.resource(
        "research://project",
        name="research_project",
        mime_type="application/json",
    )
    def project_resource() -> str:
        return _resource_document(_fresh(state).project.to_dict())

    @server.resource(
        "research://contexts",
        name="research_contexts",
        mime_type="application/json",
    )
    def context_index_resource() -> str:
        return _resource_document(_index(_fresh(state), "ResearchContext"))

    @server.resource(
        "research://contexts/{context_id}", mime_type="application/json"
    )
    def context_resource(context_id: str) -> str:
        return _manifest_resource(state, context_id, "ResearchContext")

    @server.resource(
        "research://covers/{cover_id}", mime_type="application/json"
    )
    def cover_resource(cover_id: str) -> str:
        return _manifest_resource(state, cover_id, "ResearchCover")

    @server.resource(
        "research://overlaps/{overlap_id}", mime_type="application/json"
    )
    def overlap_resource(overlap_id: str) -> str:
        return _manifest_resource(state, overlap_id, "ResearchOverlap")

    @server.resource(
        "research://claims/{claim_id}", mime_type="application/json"
    )
    def claim_resource(claim_id: str) -> str:
        return _manifest_resource(state, claim_id, "ResearchClaim")

    @server.resource(
        "research://decisions/{decision_id}", mime_type="application/json"
    )
    def decision_resource(decision_id: str) -> str:
        return _manifest_resource(state, decision_id, "ResearchDecision")

    @server.resource(
        "research://evidence/{evidence_id}", mime_type="application/json"
    )
    def evidence_resource(evidence_id: str) -> str:
        return _manifest_resource(state, evidence_id, "ResearchEvidence")

    @server.resource(
        "research://artifacts/{artifact_id}", mime_type="application/json"
    )
    def artifact_resource(artifact_id: str) -> str:
        return _manifest_resource(state, artifact_id, "ResearchArtifact")

    @server.resource("research://runs/{run_id}", mime_type="application/json")
    def run_resource(run_id: str) -> str:
        return _manifest_resource(state, run_id, "ResearchRun")

    @server.resource(
        "research://schemas/{schema_name}",
        name="research_schema",
        mime_type="application/schema+json",
    )
    def schema_resource(schema_name: str) -> str:
        if Path(schema_name).name != schema_name:
            raise ValueError("Schema name must not contain a path")
        schema = SchemaCatalog().schema(schema_name)
        return _resource_document(schema)


def _manifest_resource(
    state: ProjectState,
    record_id: str,
    kind: str,
) -> str:
    return _resource_document(_fresh(state).require(record_id, kind).to_dict())


def _register_prompts(server: MCPServer[Any], state: ProjectState) -> None:
    @server.prompt(
        name="explore_context",
        description="Bound an exploration question within project policy.",
    )
    def explore_context(question: str) -> str:
        if len(question.encode("utf-8")) > _PROMPT_MAX_BYTES:
            raise ValueError("Exploration question exceeds the input limit")
        payload = {
            "project": _fresh(state).project.id,
            "question": question,
            "known_contexts": _index(_fresh(state), "ResearchContext"),
            "acceptance": [
                "propose bounded contexts and explicit unknowns",
                "record sources, assumptions, and risks",
            ],
        }
        return _bounded_prompt("Explore", payload)

    @server.prompt(name="plan_cover")
    def plan_cover(cover_id: str) -> str:
        cover = _fresh(state).require(cover_id, "ResearchCover")
        return _bounded_prompt(
            "Plan declared cover",
            {
                "cover": cover.to_dict(),
                "acceptance": [
                    "all members and requirements resolve",
                    "required overlap contracts are explicit",
                ],
            },
        )

    @server.prompt(name="execute_context")
    def execute_context(context_id: str) -> str:
        return _context_prompt(state, context_id, "Execute")

    @server.prompt(name="verify_context")
    def verify_context(context_id: str) -> str:
        return _context_prompt(state, context_id, "Verify")

    @server.prompt(name="verify_overlap")
    def verify_overlap(overlap_id: str) -> str:
        overlap = _fresh(state).require(overlap_id, "ResearchOverlap")
        return _bounded_prompt(
            "Verify overlap",
            {
                "overlap": overlap.to_dict(),
                "acceptance": ["run only the declared built-in check types"],
            },
        )

    @server.prompt(name="glue_cover")
    def glue_cover(cover_id: str) -> str:
        cover = _fresh(state).require(cover_id, "ResearchCover")
        return _bounded_prompt(
            "Glue compatible results",
            {
                "cover": cover.to_dict(),
                "acceptance": [
                    "contexts are ready",
                    "overlaps, claims, evidence, and staleness checks pass",
                ],
            },
        )

    @server.prompt(name="project_artifact")
    def project_artifact(artifact_id: str) -> str:
        artifact = _fresh(state).require(artifact_id, "ResearchArtifact")
        return _bounded_prompt(
            "Project manifest-only artifact",
            {
                "artifact": artifact.to_dict(),
                "acceptance": [
                    "generate only the declared manifest",
                    "do not invent publication prose or scientific claims",
                ],
            },
        )


def _register_tools(server: MCPServer[Any], state: ProjectState) -> None:
    @server.tool(
        name="validate_project",
        description="Validate manifests, references, policy, and staleness.",
    )
    def validate_project_tool() -> dict[str, object]:
        return validate_project_service(state.root).to_dict()

    @server.tool(
        name="build_context_bundle",
        description="Plan or build a bounded deterministic context bundle.",
    )
    def build_context_bundle_tool(
        context_id: str,
        harness: Harness = "common",
        max_bytes: int = _PROMPT_MAX_BYTES,
        include_evidence_summary: bool = False,
        include_source_excerpts: bool = False,
        force: bool = False,
        dry_run: bool = True,
    ) -> dict[str, object]:
        return _tool_call(
            lambda: build_context(
                state.root,
                context_id,
                harness=harness,
                max_bytes=max_bytes,
                include_evidence_summary=include_evidence_summary,
                include_source_excerpts=include_source_excerpts,
                force=force,
                dry_run=dry_run,
            ).to_dict()
        )

    @server.tool(name="check_cover", description="Check a declared cover.")
    def check_cover_tool(cover_id: str) -> dict[str, object]:
        return _tool_call(
            lambda: check_cover_service(state.root, cover_id).to_dict()
        )

    @server.tool(name="check_overlap", description="Run fixed overlap checks.")
    def check_overlap_tool(overlap_id: str) -> dict[str, object]:
        return _tool_call(
            lambda: check_overlap_service(state.root, overlap_id).to_dict()
        )

    @server.tool(name="check_claim", description="Check claim evidence policy.")
    def check_claim_tool(claim_id: str) -> dict[str, object]:
        return _tool_call(
            lambda: check_claim_service(state.root, claim_id).to_dict()
        )

    @server.tool(
        name="inspect_evidence",
        description="Inspect evidence checksums without network retrieval.",
    )
    def inspect_evidence_tool(evidence_id: str) -> dict[str, object]:
        return _tool_call(
            lambda: inspect_evidence_service(state.root, evidence_id).to_dict()
        )

    @server.tool(name="start_run", description="Plan or start a lifecycle run.")
    def start_run_tool(
        phase: Phase,
        context_id: str | None = None,
        dry_run: bool = True,
    ) -> dict[str, object]:
        return _tool_call(
            lambda: start_run(
                state.root,
                phase,
                context_id=context_id,
                dry_run=dry_run,
            ).to_dict()
        )

    @server.tool(name="finish_run", description="Plan or finish an active run.")
    def finish_run_tool(
        run_id: str,
        exit_code: int,
        outputs: list[str] | None = None,
        dry_run: bool = True,
    ) -> dict[str, object]:
        return _tool_call(
            lambda: finish_run(
                state.root,
                run_id,
                exit_code,
                outputs=outputs or (),
                dry_run=dry_run,
            ).to_dict()
        )

    @server.tool(
        name="create_gluing_manifest",
        description="Create a confined manifest without merging source.",
    )
    def create_gluing_manifest_tool(
        cover_id: str,
        output: str,
        force: bool = False,
        dry_run: bool = True,
    ) -> dict[str, object]:
        return _tool_call(
            lambda: create_gluing_manifest_service(
                state.root,
                cover_id,
                output,
                force=force,
                dry_run=dry_run,
                allow_external_output=False,
            ).to_dict()
        )

    @server.tool(
        name="create_artifact_manifest",
        description="Create a confined manifest-only artifact projection.",
    )
    def create_artifact_manifest_tool(
        artifact_id: str,
        output: str,
        force: bool = False,
        dry_run: bool = True,
    ) -> dict[str, object]:
        return _tool_call(
            lambda: create_artifact_manifest_service(
                state.root,
                artifact_id,
                output,
                force=force,
                dry_run=dry_run,
                allow_external_output=False,
            ).to_dict()
        )


def _fresh(state: ProjectState) -> ProjectState:
    return load_project_state(state.root)


def _tool_call(
    operation: Callable[[], dict[str, object]],
) -> dict[str, object]:
    try:
        return operation()
    except AscOSError as error:
        raise ToolError(
            f"{error.detail.code}: {error.detail.message}"
        ) from None


def _index(state: ProjectState, kind: str) -> list[dict[str, str]]:
    return [
        {
            "id": item.id,
            "title": item.metadata.title,
            "status": item.metadata.status,
        }
        for item in state.by_kind(kind)
    ]


def _resource_document(data: object) -> str:
    return canonical_json(
        {
            "content_type": "application/json",
            "schema_version": "ai4scicomp.research/v1",
            "source_sha256": content_hash(data),
            "data": data,
        }
    )


def _context_prompt(
    state: ProjectState,
    context_id: str,
    action: str,
) -> str:
    result = build_context_plan(
        state.root,
        context_id,
        harness="common",
        max_bytes=_PROMPT_MAX_BYTES,
    )
    path = f".ai/generated/common/{context_id}/context.md"
    content = next(
        item.content for item in result.plan.writes if item.path == path
    )
    return (
        f"# {action} bounded context\n\n"
        + content
        + "\nAcceptance: satisfy the declared context criteria and validate "
        + "before "
        + "handoff.\n"
    )


def _bounded_prompt(action: str, payload: object) -> str:
    content = canonical_json(payload)
    if len(content.encode("utf-8")) > _PROMPT_MAX_BYTES:
        raise ValueError("Bounded prompt exceeds the configured size limit")
    return (
        f"# {action}\n\nUse only this bounded research payload. Do not request "
        "credentials, hidden reasoning, policy bypass, arbitrary execution, or "
        f"network retrieval.\n\n```json\n{content}\n```\n"
    )
