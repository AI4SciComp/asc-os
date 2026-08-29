"""Initial CLI identity tests."""

from pathlib import Path

import pytest

from asc_os.cli import main
from asc_os.version import __version__


def test_version_surface(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_validate_json(
    minimal_project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["validate", str(minimal_project), "--json"]) == 0
    output = capsys.readouterr().out
    assert '"valid":true' in output
