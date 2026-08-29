"""Integration tests for non-executing skill validation."""

from pathlib import Path

import pytest

from asc_os.errors import ManifestError, UnsafePathError
from asc_os.scaffold import init_project
from asc_os.skills import validate_skill


def _skill_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    init_project(root)
    schema_root = root / "schemas" / "skills"
    schema_root.mkdir(parents=True)
    for name in ("input", "output"):
        (schema_root / f"{name}.schema.json").write_text(
            '{"$schema":"https://json-schema.org/draft/2020-12/schema",'
            '"type":"object","additionalProperties":false}\n',
            encoding="utf-8",
        )
    skill = root / "research" / "skills" / "SKL-ONE.yaml"
    skill.write_text(
        """\
api_version: ai4scicomp.research/v1
kind: ResearchSkill
metadata:
  id: SKL-ONE
  title: External research procedure
  status: active
  labels: []
spec:
  version: 0.1.0
  capabilities: [explore]
  required_context_fields: [question]
  input_schema: schemas/skills/input.schema.json
  output_schema: schemas/skills/output.schema.json
  execution:
    mode: external
    trusted: false
""",
        encoding="utf-8",
    )
    return root


def test_skill_schemas_validate_without_execution(tmp_path: Path) -> None:
    root = _skill_project(tmp_path)
    hostile = root / "SHOULD_NOT_EXIST"
    report = validate_skill(root, "SKL-ONE")
    assert report.passed
    assert not hostile.exists()
    execution = next(
        item for item in report.checks if item.check_id == "execution-policy"
    )
    assert execution.message.endswith("no code was executed.")


def test_invalid_referenced_schema_is_reported(tmp_path: Path) -> None:
    root = _skill_project(tmp_path)
    (root / "schemas" / "skills" / "input.schema.json").write_text(
        '{"type":42}\n', encoding="utf-8"
    )
    report = validate_skill(root, "SKL-ONE")
    outcome = next(
        item for item in report.checks if item.check_id == "input-schema"
    )
    assert not outcome.passed


def test_skill_schema_symlink_escape_is_rejected(tmp_path: Path) -> None:
    root = _skill_project(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text('{"type":"object"}\n', encoding="utf-8")
    link = root / "schemas" / "skills" / "input.schema.json"
    link.unlink()
    link.symlink_to(outside)
    with pytest.raises(UnsafePathError):
        validate_skill(root, "SKL-ONE")


def test_executable_skill_fields_are_schema_rejected(tmp_path: Path) -> None:
    root = _skill_project(tmp_path)
    skill = root / "research" / "skills" / "SKL-ONE.yaml"
    skill.write_text(
        skill.read_text(encoding="utf-8").replace(
            "trusted: false",
            "trusted: false\n    command: 'touch SHOULD_NOT_EXIST'",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError):
        validate_skill(root, "SKL-ONE")
    assert not (root / "SHOULD_NOT_EXIST").exists()
