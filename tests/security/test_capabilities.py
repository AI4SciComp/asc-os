"""Adversarial tests for parser, write, diagnostic, and MCP boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import anyio
import pytest
from mcp import Client
from mcp_types import TextContent

from asc_os import cli
from asc_os.errors import ManifestError, WriteConflictError
from asc_os.manifest import MAX_YAML_DEPTH, load_yaml
from asc_os.mcp_server import create_server
from asc_os.scaffold import init_project
from asc_os.storage import PlannedWrite, WritePlan, apply_plan


def test_invalid_utf8_control_characters_and_deep_yaml_are_rejected(
    tmp_path: Path,
) -> None:
    """Reject hostile encoding, terminal control, and nesting inputs."""
    invalid = tmp_path / "invalid.yaml"
    invalid.write_bytes(b"value: \xff\n")
    with pytest.raises(ManifestError, match="invalid start byte"):
        load_yaml(invalid)

    controlled = tmp_path / "controlled.yaml"
    controlled.write_bytes(b"value: unsafe\x1b[31m\n")
    with pytest.raises(ManifestError, match="control character"):
        load_yaml(controlled)

    deep = tmp_path / "deep.yaml"
    deep.write_text(
        ("value: [" * (MAX_YAML_DEPTH + 1))
        + "leaf"
        + ("]" * (MAX_YAML_DEPTH + 1)),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="nesting exceeds"):
        load_yaml(deep)


def test_portable_case_collision_is_rejected(tmp_path: Path) -> None:
    """Reject plans that alias on Windows or case-insensitive volumes."""
    root = tmp_path / "project"
    plan = WritePlan(
        root=root,
        directories=(),
        writes=(
            PlannedWrite("research/Result.json", "one\n"),
            PlannedWrite("research/result.json", "two\n"),
        ),
    )
    with pytest.raises(WriteConflictError, match="portable path collision"):
        apply_plan(plan, dry_run=True)


def test_generated_ownership_spoof_does_not_authorize_overwrite(
    tmp_path: Path,
) -> None:
    """Require complete valid ownership metadata before replacement."""
    root = tmp_path / "project"
    destination = root / "output.json"
    destination.parent.mkdir()
    destination.write_text(
        '{"_asc_os":{"generator":"asc-os","source_sha256":"not-a-digest"}}\n',
        encoding="utf-8",
    )
    plan = WritePlan(
        root=root,
        directories=(),
        writes=(
            PlannedWrite(
                "output.json",
                "replacement\n",
                generated=True,
                allow_replace_owned=True,
            ),
        ),
    )
    with pytest.raises(WriteConflictError, match="hand-authored"):
        apply_plan(plan)
    assert "not-a-digest" in destination.read_text(encoding="utf-8")


def test_cli_diagnostics_escape_log_injection_and_redact_secret_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Do not emit literal newlines or token-like values from hostile IDs."""
    root = tmp_path / "project"
    init_project(root)
    monkeypatch.chdir(root)
    hostile = "CTX-MISSING\nforged ghp_" + ("A" * 30)
    assert cli.main(["context", "show", hostile]) == 5
    diagnostic = capsys.readouterr().err
    assert "\\n" in diagnostic
    assert "[REDACTED]" in diagnostic
    assert "ghp_" not in diagnostic
    assert "\nforged" not in diagnostic


def test_mcp_has_no_command_or_arbitrary_path_capability(
    tmp_path: Path,
) -> None:
    """Treat command text as data and reject undeclared tools and paths."""
    root = tmp_path / "project"
    init_project(root)
    sentinel = tmp_path / "must-not-exist"
    shell_text = f"touch {sentinel} && git reset --hard"

    async def scenario() -> None:
        async with Client(create_server(root), raise_exceptions=True) as client:
            tools = await client.list_tools()
            serialized = str([tool.input_schema for tool in tools.tools])
            assert "command" not in serialized.lower()
            prompt = await client.get_prompt(
                "explore_context", {"question": shell_text}
            )
            content = cast(TextContent, prompt.messages[0].content)
            assert shell_text in content.text
            undeclared = await client.call_tool(
                "execute_command", {"command": shell_text}
            )
            assert undeclared.is_error
            escaped = await client.call_tool(
                "create_artifact_manifest",
                {
                    "artifact_id": "ART-MISSING",
                    "output": str(tmp_path / "outside.json"),
                    "dry_run": False,
                },
            )
            assert escaped.is_error

    anyio.run(scenario)
    assert not sentinel.exists()
    assert not (tmp_path / "outside.json").exists()
