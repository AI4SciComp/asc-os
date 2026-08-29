"""Direct contract tests for every read and projection CLI family."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from asc_os import cli

_PILOT = Path(__file__).resolve().parents[2] / "examples" / "ap-kinetic-study"


@pytest.fixture
def pilot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Copy the public pilot and enter its root."""
    root = tmp_path / "pilot"
    shutil.copytree(_PILOT, root)
    monkeypatch.chdir(root)
    return root


@pytest.mark.parametrize(
    "arguments",
    (
        ["cover", "check", "COV-0001", "--json"],
        ["overlap", "check", "OVL-ASYMPTOTIC-ORBIT", "--json"],
        ["claim", "list", "--status", "verified", "--json"],
        ["claim", "show", "CLM-ORBIT-AP", "--json"],
        ["claim", "check", "CLM-ORBIT-AP", "--json"],
        ["decision", "list", "--status", "accepted", "--json"],
        ["decision", "show", "DEC-ENERGY", "--json"],
        ["evidence", "show", "EVD-ORBIT-DERIVATION", "--json"],
        ["evidence", "verify", "EVD-ORBIT-DERIVATION", "--json"],
        ["glue", "check", "COV-0001", "--json"],
        ["artifact", "check", "ART-PAPER", "--json"],
        ["skill", "validate", "SKL-REVIEW", "--json"],
    ),
)
def test_read_and_check_commands_succeed(
    pilot: Path,
    arguments: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep each public inspection family wired to its typed service."""
    assert pilot.is_dir()
    assert cli.main(arguments) == 0
    assert capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments",
    (
        [
            "glue",
            "manifest",
            "COV-0001",
            "--output",
            "build/glue/COV-0001.json",
            "--dry-run",
            "--json",
        ],
        [
            "artifact",
            "manifest",
            "ART-PAPER",
            "--output",
            "build/artifacts/paper-manifest.json",
            "--dry-run",
            "--json",
        ],
    ),
)
def test_projection_commands_default_to_reviewable_plans(
    pilot: Path,
    arguments: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep projection output dry-run-only when explicitly requested."""
    assert cli.main(arguments) == 0
    output = capsys.readouterr().out
    assert '"writes"' in output
    assert not (pilot / "build").exists()
