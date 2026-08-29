"""Declared-cover and fixed-vocabulary overlap verification."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from asc_os.canonical import canonical_json, file_hash
from asc_os.errors import ManifestError, ReferenceIntegrityError
from asc_os.manifest import (
    ProjectState,
    SchemaCatalog,
    load_manifest,
    load_project_state,
    load_yaml,
)
from asc_os.paths import confined_path, relative_posix

_STATUS_RANK = {
    "draft": 0,
    "planned": 1,
    "active": 2,
    "completed": 3,
    "verified": 4,
}


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """One deterministic validation outcome."""

    check_id: str
    check_type: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class CoverReport:
    """Declared coverage result for one cover."""

    cover_id: str
    passed: bool
    checks: tuple[CheckOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable report data."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OverlapReport:
    """Compatibility result for one overlap contract."""

    overlap_id: str
    left: str
    right: str
    passed: bool
    checks: tuple[CheckOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible stable report data."""
        return asdict(self)


def check_cover(
    project_path: str | Path,
    cover_id: str,
) -> CoverReport:
    """Check one declared cover without inferring semantic completeness."""
    state = load_project_state(project_path)
    cover = state.require(cover_id, "ResearchCover")
    members = set(_string_list(cover.spec["members"]))
    requirements = cast(Mapping[str, Iterable[str]], cover.spec["requirements"])
    outcomes: list[CheckOutcome] = [
        CheckOutcome(
            "members-declared",
            "cover_members",
            bool(members),
            (
                f"{len(members)} member context(s) are declared."
                if members
                else "The cover declares no member contexts."
            ),
        )
    ]
    for name, values in sorted(requirements.items()):
        declared = tuple(sorted(values))
        missing = tuple(item for item in declared if item not in members)
        passed = bool(declared) and not missing
        message = (
            f"Requirement {name!r} is covered by {', '.join(declared)}."
            if passed
            else (
                f"Requirement {name!r} is empty or references non-members: "
                + ", ".join(missing)
            )
        )
        outcomes.append(
            CheckOutcome(
                f"requirement:{name}", "cover_requirement", passed, message
            )
        )
    allowed_endpoints = {cast(str, cover.spec["target"]), *members}
    for overlap_id in _string_list(cover.spec["required_overlaps"]):
        overlap = state.require(overlap_id, "ResearchOverlap")
        endpoints = {
            cast(str, overlap.spec["left"]),
            cast(str, overlap.spec["right"]),
        }
        passed = endpoints <= allowed_endpoints
        outcomes.append(
            CheckOutcome(
                f"overlap:{overlap_id}",
                "cover_overlap_boundary",
                passed,
                (
                    "Required overlap endpoints are inside the declared cover."
                    if passed
                    else "Required overlap references a context outside the "
                    "cover."
                ),
            )
        )
    ordered = tuple(sorted(outcomes, key=lambda item: item.check_id))
    return CoverReport(cover.id, all(item.passed for item in ordered), ordered)


def check_overlap(
    project_path: str | Path,
    overlap_id: str,
) -> OverlapReport:
    """Evaluate one overlap using only the eight built-in check types."""
    state = load_project_state(project_path)
    overlap = state.require(overlap_id, "ResearchOverlap")
    checks = cast(Iterable[Mapping[str, Any]], overlap.spec["checks"])
    outcomes = tuple(_evaluate_check(state, item) for item in checks)
    return OverlapReport(
        overlap.id,
        cast(str, overlap.spec["left"]),
        cast(str, overlap.spec["right"]),
        all(item.passed for item in outcomes),
        outcomes,
    )


def _evaluate_check(
    state: ProjectState,
    check: Mapping[str, Any],
) -> CheckOutcome:
    check_id = cast(str, check["id"])
    check_type = cast(str, check["type"])
    try:
        passed, message = _dispatch_check(state, check_type, check)
    except (
        KeyError,
        TypeError,
        ValueError,
        IndexError,
        ManifestError,
        ReferenceIntegrityError,
    ) as error:
        passed = False
        message = f"Invalid {check_type} operands: {error}"
    return CheckOutcome(check_id, check_type, passed, message)


def _dispatch_check(  # noqa: PLR0911
    state: ProjectState,
    check_type: str,
    check: Mapping[str, Any],
) -> tuple[bool, str]:
    if check_type == "value_equal":
        left = _load_operand(state, _mapping(check["left"]))
        right = _load_operand(state, _mapping(check["right"]))
        passed = canonical_json(left) == canonical_json(right)
        return passed, "Values are equal." if passed else "Values differ."
    if check_type == "set_equal":
        left = _canonical_set(_load_operand(state, _mapping(check["left"])))
        right = _canonical_set(_load_operand(state, _mapping(check["right"])))
        passed = left == right
        return passed, "Sets are equal." if passed else "Sets differ."
    if check_type == "ordered_list_equal":
        left = _sequence(_load_operand(state, _mapping(check["left"])))
        right = _sequence(_load_operand(state, _mapping(check["right"])))
        passed = canonical_json(left) == canonical_json(right)
        return (
            passed,
            "Ordered lists are equal." if passed else "Ordered lists differ.",
        )
    if check_type == "content_hash_equal":
        left_path = _operand_path(state, _mapping(check["left"]))
        right_path = _operand_path(state, _mapping(check["right"]))
        passed = file_hash(left_path) == file_hash(right_path)
        return (
            passed,
            "Exact content hashes are equal."
            if passed
            else "Exact content hashes differ.",
        )
    if check_type == "reference_resolves":
        reference = cast(str, check["reference"])
        kind = cast(str | None, check.get("kind"))
        state.require(reference, kind)
        return True, f"Reference {reference!r} resolves."
    if check_type == "schema_valid":
        path = _operand_path(state, _mapping(check["left"]))
        load_manifest(path, SchemaCatalog())
        return True, f"{relative_posix(state.root, path)!r} is schema-valid."
    if check_type == "claim_status_at_least":
        reference = cast(str, check["reference"])
        minimum = cast(str, check["minimum_status"])
        claim = state.require(reference, "ResearchClaim")
        passed = _status_at_least(claim.metadata.status, minimum)
        return (
            passed,
            f"Claim status {claim.metadata.status!r} "
            + ("meets" if passed else "does not meet")
            + f" minimum {minimum!r}.",
        )
    if check_type == "file_exists":
        path = _operand_path(state, _mapping(check["left"]), must_exist=False)
        passed = path.is_file()
        return (
            passed,
            f"File {relative_posix(state.root, path)!r} "
            + ("exists." if passed else "does not exist."),
        )
    raise ValueError(f"unsupported built-in check type {check_type!r}")


def _load_operand(state: ProjectState, operand: Mapping[str, Any]) -> Any:
    path = _operand_path(state, operand)
    value = load_yaml(path)
    pointer = operand.get("pointer")
    if isinstance(pointer, str):
        return _resolve_pointer(value, pointer)
    return value


def _operand_path(
    state: ProjectState,
    operand: Mapping[str, Any],
    *,
    must_exist: bool = True,
) -> Path:
    return confined_path(
        state.root,
        cast(str, operand["file"]),
        must_exist=must_exist,
    )


def _resolve_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must start with '/'")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            current = cast(Mapping[str, Any], current)[token]
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes)
        ):
            current = cast(Sequence[Any], current)[int(token)]
        else:
            raise TypeError(f"cannot traverse token {token!r}")
    return current


def _canonical_set(value: Any) -> frozenset[str]:
    return frozenset(canonical_json(item) for item in _sequence(value))


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return cast(Sequence[Any], value)
    raise TypeError("operand must be a list")


def _status_at_least(actual: str, minimum: str) -> bool:
    if actual not in _STATUS_RANK or minimum not in _STATUS_RANK:
        return False
    return _STATUS_RANK[actual] >= _STATUS_RANK[minimum]


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value)


def _string_list(value: object) -> tuple[str, ...]:
    return tuple(cast(Iterable[str], value))
