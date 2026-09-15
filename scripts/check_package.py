"""Exercise built distributions as installed tools outside the checkout."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast
from zipfile import ZipFile

from asc_os.version import __version__


def _require(condition: bool, message: str) -> None:
    """Stop package validation when a required property is absent."""
    if not condition:
        raise SystemExit(message)


def _run(arguments: list[str], cwd: Path, environment: dict[str, str]) -> str:
    """Run a fixed validation command and report captured failures."""
    result = subprocess.run(  # noqa: S603 - no shell or manifest arguments.
        arguments,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    _require(
        result.returncode == 0,
        f"Command failed: {arguments!r}\n{result.stdout}\n{result.stderr}",
    )
    return result.stdout.strip()


def _check_resources(repository: Path, wheel: Path) -> None:
    """Compare packaged schema and template bytes with the source catalog."""
    with ZipFile(wheel) as archive:
        for directory in ("schemas", "templates"):
            for source in sorted((repository / directory).rglob("*")):
                if source.is_file():
                    relative = source.relative_to(repository).as_posix()
                    _require(
                        archive.read(f"asc_os/{relative}")
                        == source.read_bytes(),
                        f"Packaged resource differs: {relative}",
                    )
        _require("asc_os/py.typed" in archive.namelist(), "Missing py.typed")


def _check_install(uv: str, distribution: Path, *, mcp: bool) -> None:
    """Install one distribution and exercise the public console entrypoint."""
    with tempfile.TemporaryDirectory(prefix="asc-os-package-") as temporary:
        workspace = Path(temporary)
        tool_bin = workspace / "bin"
        environment = dict(os.environ)
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            environment.pop(name, None)
        environment.update(
            UV_TOOL_DIR=str(workspace / "tools"),
            UV_TOOL_BIN_DIR=str(tool_bin),
            PATH=os.pathsep.join((str(tool_bin), environment.get("PATH", ""))),
        )
        package = f"{distribution}[mcp]" if mcp else str(distribution)
        _run(
            [uv, "tool", "install", "--python", sys.executable, package],
            workspace,
            environment,
        )
        executable = shutil.which("asc-os", path=str(tool_bin))
        if executable is None:
            raise SystemExit("Installed distribution has no asc-os command")

        def cli(*arguments: str, cwd: Path = workspace) -> dict[str, Any]:
            return cast(
                dict[str, Any],
                json.loads(
                    _run([executable, *arguments, "--json"], cwd, environment)
                ),
            )

        version = _run([executable, "--version"], workspace, environment)
        _require(version == __version__, "Installed CLI version differs")
        doctor = cli("doctor")
        _require(doctor["mcp_sdk"] is mcp, "Incorrect MCP extra state")
        project = workspace / "study with spaces"
        cli("init", str(project), "--dry-run")
        _require(not project.exists(), "Init dry-run wrote a project")
        cli("init", str(project))
        _require(cli("validate", str(project))["valid"], "Validation failed")
        nested = project / "research" / "contexts" / "root"
        _require(cli("validate", cwd=nested)["valid"], "Discovery failed")
        arguments = ("context", "build", "CTX-ROOT", "--harness", "codex")
        cli(*arguments, "--dry-run", cwd=nested)
        generated = project / ".ai" / "generated"
        _require(not any(generated.rglob("*.json")), "Build dry-run wrote")
        cli(*arguments, cwd=nested)
        second = cli(*arguments, cwd=nested)
        _require(second["plan"]["noop"], "Second build was not a no-op")
        _require(cli("validate", cwd=nested)["valid"], "Built state invalid")
        (project / "research" / "notation.yaml").write_text(
            "symbols: {x: updated}\n", encoding="utf-8"
        )
        cli(*arguments, "--force", "--dry-run", cwd=nested)
        cli(*arguments, "--force", cwd=nested)
        _require(cli("validate", cwd=nested)["valid"], "Rebuilt state invalid")
    print(f"Installed {distribution.name} (mcp={mcp}): passed")


def main() -> int:
    """Validate current-version wheel and source distributions in isolation."""
    repository = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required for installed-package validation")
    wheel = repository / "dist" / f"asc_os-{__version__}-py3-none-any.whl"
    source = repository / "dist" / f"asc_os-{__version__}.tar.gz"
    for distribution in (wheel, source):
        _require(distribution.is_file(), f"Run make build: {distribution}")
    _check_resources(repository, wheel)
    _check_install(uv, wheel, mcp=False)
    _check_install(uv, source, mcp=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
