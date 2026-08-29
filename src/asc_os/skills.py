"""Declarative skill discovery and schema validation without execution."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import jsonschema

from asc_os.manifest import load_project_state
from asc_os.paths import confined_path, relative_posix
from asc_os.verification import CheckOutcome

_MAX_SKILL_SCHEMA_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SkillReport:
    """Descriptive skill and referenced-schema validation report."""

    skill_id: str
    passed: bool
    checks: tuple[CheckOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable report data."""
        return asdict(self)


def validate_skill(
    project_path: str | Path,
    skill_id: str,
) -> SkillReport:
    """Validate a skill manifest and schemas without executing it."""
    state = load_project_state(project_path)
    skill = state.require(skill_id, "ResearchSkill")
    outcomes: list[CheckOutcome] = []
    for field in ("input_schema", "output_schema"):
        relative = cast(str, skill.spec[field])
        path = confined_path(state.root, relative, must_exist=True)
        passed, message = _validate_schema(path)
        outcomes.append(
            CheckOutcome(
                field.replace("_", "-"),
                "skill_json_schema",
                passed,
                f"{relative_posix(state.root, path)!r}: {message}",
            )
        )
    execution = cast(dict[str, Any], skill.spec["execution"])
    safe = (
        execution.get("mode") == "external"
        and execution.get("trusted") is False
    )
    outcomes.append(
        CheckOutcome(
            "execution-policy",
            "skill_non_execution",
            safe,
            (
                "Skill remains external and untrusted; no code was executed."
                if safe
                else "Skill execution policy is unsafe."
            ),
        )
    )
    ordered = tuple(sorted(outcomes, key=lambda item: item.check_id))
    return SkillReport(skill.id, all(item.passed for item in ordered), ordered)


def _validate_schema(path: Path) -> tuple[bool, str]:
    try:
        payload = path.read_bytes()
        if len(payload) > _MAX_SKILL_SCHEMA_BYTES:
            return False, f"schema exceeds {_MAX_SKILL_SCHEMA_BYTES} bytes"
        parsed: object = json.loads(payload.decode("utf-8", errors="strict"))
        jsonschema.Draft202012Validator.check_schema(
            cast(dict[str, Any], parsed)
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        jsonschema.SchemaError,
    ) as error:
        return False, str(error)
    return True, "valid Draft 2020-12 schema"
