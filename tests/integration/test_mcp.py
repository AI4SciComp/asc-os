"""Official SDK integration tests for the confined local MCP server."""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError
from mcp_types import TextContent, TextResourceContents

from asc_os.mcp_server import create_server
from asc_os.scaffold import init_project

_TOOL_NAMES = {
    "validate_project",
    "build_context_bundle",
    "check_cover",
    "check_overlap",
    "check_claim",
    "inspect_evidence",
    "start_run",
    "finish_run",
    "create_gluing_manifest",
    "create_artifact_manifest",
}
_PROMPT_NAMES = {
    "explore_context",
    "plan_cover",
    "execute_context",
    "verify_context",
    "verify_overlap",
    "glue_cover",
    "project_artifact",
}


def test_resource_prompt_and_tool_catalogs(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)

    async def scenario() -> None:
        async with Client(create_server(root), raise_exceptions=True) as client:
            resources = await client.list_resources()
            assert {str(item.uri) for item in resources.resources} == {
                "research://project",
                "research://contexts",
            }
            templates = await client.list_resource_templates()
            assert len(templates.resource_templates) == 9
            tools = await client.list_tools()
            assert {item.name for item in tools.tools} == _TOOL_NAMES
            prompts = await client.list_prompts()
            assert {item.name for item in prompts.prompts} == _PROMPT_NAMES
            for tool in tools.tools:
                schema = json.dumps(tool.input_schema, sort_keys=True)
                assert "command" not in schema
                assert "credential" not in schema
                assert "network" not in schema
            write_tools = {
                "build_context_bundle",
                "start_run",
                "finish_run",
                "create_gluing_manifest",
                "create_artifact_manifest",
            }
            for tool in tools.tools:
                if tool.name in write_tools:
                    properties = cast(
                        dict[str, object], tool.input_schema["properties"]
                    )
                    assert "dry_run" in properties

    anyio.run(scenario)


def test_resources_include_schema_version_type_and_hash(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)

    async def scenario() -> None:
        async with Client(create_server(root), raise_exceptions=True) as client:
            project = await client.read_resource("research://project")
            content = cast(TextResourceContents, project.contents[0])
            payload = cast(dict[str, Any], json.loads(content.text))
            assert payload["content_type"] == "application/json"
            assert payload["schema_version"] == "ai4scicomp.research/v1"
            assert len(cast(str, payload["source_sha256"])) == 64
            context = await client.read_resource("research://contexts/CTX-ROOT")
            context_content = cast(TextResourceContents, context.contents[0])
            assert "CTX-ROOT" in context_content.text
            schema = await client.read_resource(
                "research://schemas/context.schema.json"
            )
            schema_content = cast(TextResourceContents, schema.contents[0])
            assert "2020-12" in schema_content.text

    anyio.run(scenario)


def test_prompts_are_bounded_and_policy_preserving(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)

    async def scenario() -> None:
        async with Client(create_server(root), raise_exceptions=True) as client:
            first = await client.get_prompt(
                "execute_context", {"context_id": "CTX-ROOT"}
            )
            second = await client.get_prompt(
                "execute_context", {"context_id": "CTX-ROOT"}
            )
            first_content = cast(TextContent, first.messages[0].content)
            second_content = cast(TextContent, second.messages[0].content)
            assert first_content.text == second_content.text
            assert "Acceptance:" in first_content.text
            exploration = await client.get_prompt(
                "explore_context", {"question": "What is bounded?"}
            )
            exploration_content = cast(
                TextContent, exploration.messages[0].content
            )
            assert "hidden reasoning" in exploration_content.text
            assert "credential" in exploration_content.text

    anyio.run(scenario)


def test_tools_are_deterministic_and_dry_run_by_default(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)

    async def scenario() -> None:
        async with Client(create_server(root), raise_exceptions=True) as client:
            first = await client.call_tool("validate_project")
            second = await client.call_tool("validate_project")
            assert first.structured_content == second.structured_content
            build = await client.call_tool(
                "build_context_bundle",
                {"context_id": "CTX-ROOT", "harness": "codex"},
            )
            assert not build.is_error
            assert not any((root / ".ai" / "generated" / "common").iterdir())
            applied = await client.call_tool(
                "build_context_bundle",
                {
                    "context_id": "CTX-ROOT",
                    "harness": "codex",
                    "dry_run": False,
                },
            )
            assert not applied.is_error
            assert (
                root
                / ".ai"
                / "generated"
                / "common"
                / "CTX-ROOT"
                / "context.json"
            ).is_file()
        assert not (root / ".asc-os.lock").exists()

    anyio.run(scenario)


def test_malformed_oversized_and_escape_requests_are_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    init_project(root)

    async def scenario() -> None:
        async with Client(create_server(root), raise_exceptions=True) as client:
            malformed = await client.call_tool(
                "build_context_bundle",
                {"context_id": "CTX-ROOT", "harness": "network"},
            )
            assert malformed.is_error
            oversized = await client.call_tool(
                "build_context_bundle",
                {"context_id": "CTX-ROOT", "max_bytes": 1},
            )
            assert oversized.is_error
            assert (
                "context_size_exceeded"
                in cast(TextContent, oversized.content[0]).text
            )
            with pytest.raises(MCPError):
                await client.read_resource("research://schemas/../secret")
            escaped = await client.call_tool(
                "create_gluing_manifest",
                {
                    "cover_id": "COV-MISSING",
                    "output": "../outside.json",
                },
            )
            assert escaped.is_error
        assert not (tmp_path / "outside.json").exists()

    anyio.run(scenario)


def test_cancellation_and_shutdown_leave_no_partial_write(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    init_project(root)

    async def scenario() -> None:
        async with Client(create_server(root), raise_exceptions=True) as client:
            with anyio.CancelScope() as scope:
                scope.cancel()
                await client.call_tool(
                    "build_context_bundle",
                    {"context_id": "CTX-ROOT", "dry_run": False},
                )
            healthy = await client.call_tool("validate_project")
            assert not healthy.is_error
        assert not (root / ".asc-os.lock").exists()
        assert not list(root.rglob("*.tmp"))

    anyio.run(scenario)


def test_in_process_transport_opens_no_network_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    init_project(root)
    server = create_server(root)

    async def scenario() -> None:
        def reject_socket(*_args: object, **_kwargs: object) -> socket.socket:
            raise AssertionError("network socket creation is forbidden")

        monkeypatch.setattr(socket, "socket", reject_socket)
        async with Client(server, raise_exceptions=True) as client:
            result = await client.call_tool("validate_project")
            assert not result.is_error

    anyio.run(scenario)


def test_stdio_transport_with_official_client(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "asc_os",
            "mcp",
            "serve",
            "--transport",
            "stdio",
            "--project",
            str(root),
        ],
        cwd=Path(__file__).resolve().parents[2],
    )

    async def scenario() -> None:
        async with Client(parameters, raise_exceptions=True) as client:
            result = await client.call_tool("validate_project")
            payload = cast(dict[str, Any], result.structured_content)
            assert payload["valid"] is True

    anyio.run(scenario)


def test_server_requires_explicit_project_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    init_project(root)
    with pytest.raises(ValueError, match="explicit project root"):
        create_server(root / "research")
