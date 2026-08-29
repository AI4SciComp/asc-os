"""Tests for safe manifests and reference integrity."""

from pathlib import Path

import pytest

from asc_os.api import load_project, validate_project
from asc_os.errors import ManifestError, ReferenceIntegrityError
from asc_os.manifest import SchemaCatalog, load_manifest, load_yaml


def test_load_project_builds_typed_index(minimal_project: Path) -> None:
    state = load_project(minimal_project)
    assert state.project.id == "PRJ-0001"
    assert state.require("CTX-ROOT").metadata.title == "Root context"
    assert len(state.manifests) == 2
    assert validate_project(minimal_project).valid


def test_duplicate_yaml_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("key: one\nkey: two\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="duplicate key"):
        load_yaml(path)


def test_yaml_object_tag_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "tag.yaml"
    path.write_text("!!python/object/apply:os.system ['echo unsafe']\n")
    with pytest.raises(
        ManifestError, match="could not determine a constructor"
    ):
        load_yaml(path)


def test_yaml_alias_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "alias.yaml"
    path.write_text("one: &item value\ntwo: *item\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="aliases are disabled"):
        load_yaml(path)


def test_manifest_size_limit_is_enforced(tmp_path: Path) -> None:
    path = tmp_path / "large.yaml"
    path.write_text("value: " + ("x" * 100), encoding="utf-8")
    with pytest.raises(ManifestError) as caught:
        load_yaml(path, max_bytes=10)
    assert caught.value.detail.code == "manifest_too_large"


def test_unsupported_api_version_has_stable_exit(
    minimal_project: Path,
) -> None:
    path = minimal_project / "research" / "project.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "ai4scicomp.research/v1", "ai4scicomp.research/v2"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError) as caught:
        load_manifest(path, SchemaCatalog())
    assert caught.value.exit_code == 10


def test_unknown_top_level_field_is_rejected(minimal_project: Path) -> None:
    path = minimal_project / "research" / "project.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "extra: false\n")
    with pytest.raises(ManifestError) as caught:
        load_manifest(path)
    assert caught.value.detail.code == "schema_validation_failed"


def test_invalid_id_prefix_is_rejected(minimal_project: Path) -> None:
    path = minimal_project / "research" / "project.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("PRJ-0001", "CTX-0001"),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError) as caught:
        load_manifest(path)
    assert caught.value.detail.code == "invalid_id_prefix"


def test_unresolved_reference_is_rejected(minimal_project: Path) -> None:
    path = minimal_project / "research" / "project.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("CTX-ROOT", "CTX-MISSING"),
        encoding="utf-8",
    )
    with pytest.raises(ReferenceIntegrityError, match="does not resolve"):
        load_project(minimal_project)


def test_context_cycle_is_rejected(minimal_project: Path) -> None:
    path = minimal_project / "research" / "contexts" / "root" / "context.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "parent: null", "parent: CTX-ROOT"
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ReferenceIntegrityError, match="Forbidden reference cycle"
    ):
        load_project(minimal_project)
