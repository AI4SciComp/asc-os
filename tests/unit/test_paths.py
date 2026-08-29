"""Tests for root discovery and path confinement."""

from pathlib import Path

import pytest

from asc_os.errors import ProjectNotFoundError, UnsafePathError
from asc_os.paths import confined_path, find_project_root


def test_find_project_root_from_descendant(minimal_project: Path) -> None:
    descendant = minimal_project / "research" / "contexts" / "root"
    assert find_project_root(descendant) == minimal_project


def test_find_project_root_rejects_uninitialized(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError) as caught:
        find_project_root(tmp_path)
    assert caught.value.exit_code == 3


@pytest.mark.parametrize("value", ["../outside", "/tmp/outside", "a/../../b"])
def test_confined_path_rejects_unsafe_values(
    minimal_project: Path,
    value: str,
) -> None:
    with pytest.raises(UnsafePathError):
        confined_path(minimal_project, value)


def test_confined_path_rejects_outside_symlink(
    minimal_project: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    link = minimal_project / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        confined_path(minimal_project, "link/secret.txt")
