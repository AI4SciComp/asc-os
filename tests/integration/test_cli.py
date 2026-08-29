"""Integration tests for the complete CLI contract and stable exit codes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from asc_os import cli
from asc_os.context import build_context
from asc_os.scaffold import init_project, scaffold_manifest

_TOP_LEVEL_COMMANDS = (
    "doctor",
    "init",
    "validate",
    "scaffold",
    "context",
    "cover",
    "overlap",
    "claim",
    "decision",
    "evidence",
    "run",
    "glue",
    "artifact",
    "skill",
    "mcp",
)


@pytest.mark.parametrize("command", _TOP_LEVEL_COMMANDS)
def test_every_top_level_command_has_help(command: str) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main([command, "--help"])
    assert caught.value.code == 0


def test_doctor_json_is_deterministic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["doctor", "--json"]) == 0
    first = capsys.readouterr().out
    assert cli.main(["doctor", "--json"]) == 0
    second = capsys.readouterr().out
    assert first == second
    assert '"transport":"stdio-only"' in first


def test_init_validate_context_and_scaffold_dry_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "project"
    assert cli.main(["init", str(root), "--dry-run", "--json"]) == 0
    assert not root.exists()
    assert cli.main(["init", str(root), "--json"]) == 0
    capsys.readouterr()
    monkeypatch.chdir(root)
    assert cli.main(["validate", "--json"]) == 0
    assert cli.main(["context", "list", "--json"]) == 0
    assert cli.main(["context", "show", "CTX-ROOT", "--json"]) == 0
    assert (
        cli.main(
            [
                "context",
                "build",
                "CTX-ROOT",
                "--harness",
                "codex",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    assert not any((root / ".ai" / "generated" / "common").iterdir())
    scaffold_commands = (
        ["context", "--id", "CTX-ONE", "--title", "One"],
        ["cover", "--id", "COV-ONE", "--title", "One"],
        [
            "overlap",
            "--id",
            "OVL-ONE",
            "--left",
            "CTX-ROOT",
            "--right",
            "CTX-ONE",
        ],
        ["claim", "--id", "CLM-ONE", "--title", "One"],
        ["decision", "--id", "DEC-ONE", "--title", "One"],
        ["evidence", "--id", "EVD-ONE", "--type", "unit_test"],
        ["artifact", "--id", "ART-ONE", "--type", "report"],
    )
    for arguments in scaffold_commands:
        assert cli.main(["scaffold", *arguments, "--dry-run", "--json"]) == 0
    assert cli.main(["claim", "list", "--json"]) == 0
    assert cli.main(["decision", "list", "--json"]) == 0
    assert cli.main(["cover", "list", "--json"]) == 0
    assert cli.main(["overlap", "list", "--json"]) == 0
    assert cli.main(["skill", "list", "--json"]) == 0
    assert (
        cli.main(["run", "start", "--phase", "explore", "--dry-run", "--json"])
        == 0
    )


def test_usage_and_project_not_found_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit) as usage:
        cli.main(["context", "build"])
    assert usage.value.code == 2
    monkeypatch.chdir(tmp_path)
    assert cli.main(["context", "list", "--json"]) == 3


@pytest.mark.parametrize(
    ("replacement", "expected"),
    (
        ("extra: false\n", 4),
        ("root_context: CTX-MISSING\n", 5),
        ("api_version: ai4scicomp.research/v2\n", 10),
    ),
)
def test_validation_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
    expected: int,
) -> None:
    root = tmp_path / f"project-{expected}"
    init_project(root)
    project = root / "research" / "project.yaml"
    text = project.read_text(encoding="utf-8")
    if expected == 4:
        project.write_text(text + replacement, encoding="utf-8")
    elif expected == 5:
        project.write_text(
            text.replace("root_context: CTX-ROOT\n", replacement),
            encoding="utf-8",
        )
    else:
        project.write_text(
            text.replace("api_version: ai4scicomp.research/v1\n", replacement),
            encoding="utf-8",
        )
    monkeypatch.chdir(root)
    assert cli.main(["validate", "--json"]) == expected


def test_compatibility_and_stale_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    init_project(root)
    scaffold_manifest(
        root,
        "context",
        "CTX-CHILD",
        "Child",
        parent="CTX-ROOT",
    )
    scaffold_manifest(
        root,
        "overlap",
        "OVL-ONE",
        "Overlap",
        left="CTX-ROOT",
        right="CTX-CHILD",
    )
    overlap = root / "research" / "overlaps" / "OVL-ONE.yaml"
    overlap.write_text(
        overlap.read_text(encoding="utf-8").replace(
            "research/notation.yaml",
            "research/missing.yaml",
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    assert cli.main(["overlap", "check", "OVL-ONE", "--json"]) == 6
    overlap.write_text(
        overlap.read_text(encoding="utf-8").replace(
            "research/missing.yaml",
            "research/notation.yaml",
        ),
        encoding="utf-8",
    )
    build_context(root, "CTX-ROOT")
    (root / "research" / "notation.yaml").write_text(
        "symbols: {changed: true}\n", encoding="utf-8"
    )
    assert cli.main(["validate", "--json"]) == 7


def test_unsafe_write_conflict_and_evidence_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "README.md").write_text("existing\n", encoding="utf-8")
    assert cli.main(["init", str(nonempty), "--json"]) == 9

    root = tmp_path / "project"
    init_project(root)
    scaffold_manifest(root, "artifact", "ART-ONE", "Artifact")
    scaffold_manifest(
        root,
        "evidence",
        "EVD-ONE",
        "Evidence",
        evidence_type="unit_test",
    )
    monkeypatch.chdir(root)
    assert (
        cli.main(
            [
                "artifact",
                "manifest",
                "ART-ONE",
                "--output",
                "../outside.json",
                "--dry-run",
                "--json",
            ]
        )
        == 8
    )
    assert cli.main(["evidence", "verify", "EVD-ONE", "--json"]) == 11


def test_internal_error_exit_is_stable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(_args: object) -> int:
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(cli, "_handle_doctor", cast_handler(fail))
    assert cli.main(["doctor", "--json"]) == 12
    assert '"code":"internal_error"' in capsys.readouterr().out


def cast_handler(value: Callable[[object], int]) -> Callable[..., int]:
    """Give monkeypatch a handler-shaped callable without using Any."""
    return value
