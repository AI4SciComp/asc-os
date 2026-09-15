"""Tests for safe manifests and reference integrity."""

import shutil
from pathlib import Path

import pytest

from asc_os import manifest
from asc_os.api import load_project, validate_project
from asc_os.errors import ManifestError, ReferenceIntegrityError
from asc_os.manifest import SchemaCatalog, load_manifest, load_yaml
from asc_os.scaffold import scaffold_manifest


def test_installed_schema_catalog_without_source_checkout(
    minimal_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = SchemaCatalog().root
    package = tmp_path / "environment/lib/site-packages/asc_os"
    installed = package / "schemas/v1"
    shutil.copytree(source, installed)
    monkeypatch.setattr(manifest, "__file__", str(package / "manifest.py"))
    assert SchemaCatalog().root == installed
    assert validate_project(minimal_project).valid
    shutil.rmtree(installed)
    with pytest.raises(RuntimeError, match="Bundled v1 schemas are missing"):
        SchemaCatalog()


def test_incomplete_schema_catalog_fails_explicitly(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Bundled common schema is missing"):
        SchemaCatalog(tmp_path)
    with pytest.raises(ManifestError) as caught:
        SchemaCatalog().schema("missing.schema.json")
    assert caught.value.detail.code == "schema_not_found"


@pytest.mark.parametrize(
    ("text", "code"),
    (
        ("[]", "manifest_not_mapping"),
        (
            "api_version: ai4scicomp.research/v1\nkind: Unknown\n",
            "unknown_manifest_kind",
        ),
    ),
)
def test_invalid_manifest_envelope_fails(
    tmp_path: Path, text: str, code: str
) -> None:
    path = tmp_path / "manifest.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ManifestError) as caught:
        load_manifest(path)
    assert caught.value.detail.code == code


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


def test_duplicate_context_identity_is_rejected(minimal_project: Path) -> None:
    source = minimal_project / "research/contexts/root"
    shutil.copytree(source, source.with_name("duplicate"))
    with pytest.raises(ReferenceIntegrityError) as caught:
        load_project(minimal_project)
    assert caught.value.detail.code == "duplicate_id"


def test_self_overlap_is_rejected(minimal_project: Path) -> None:
    scaffold_manifest(
        minimal_project,
        "overlap",
        "OVL-SELF",
        "Self overlap",
        left="CTX-ROOT",
        right="CTX-ROOT",
    )
    with pytest.raises(ReferenceIntegrityError) as caught:
        load_project(minimal_project)
    assert caught.value.detail.code == "self_overlap"


def test_nonmapping_auxiliary_state_is_rejected(minimal_project: Path) -> None:
    (minimal_project / "research/notation.yaml").write_text("[]\n")
    with pytest.raises(ManifestError) as caught:
        load_project(minimal_project)
    assert caught.value.detail.code == "auxiliary_not_mapping"


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
