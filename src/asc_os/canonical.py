"""Deterministic canonical JSON and SHA-256 content addressing."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from collections.abc import Mapping, Sequence, Set
from pathlib import Path
from typing import Any, cast

from asc_os.manifest import Manifest

_SET_LIKE_KEYS = frozenset(
    {
        "affected_contexts",
        "artifact_targets",
        "assumptions",
        "capabilities",
        "claims",
        "contexts",
        "contradicts",
        "depends_on",
        "evidence",
        "labels",
        "members",
        "required_context_fields",
        "required_covers",
        "required_evidence_classes",
        "required_overlaps",
        "supports",
        "supersedes",
    }
)


def canonical_data(  # noqa: PLR0911
    value: Any,
    *,
    field: str | None = None,
) -> Any:
    """Convert a value to deterministic JSON-compatible data.

    Args:
        value: Validated model or JSON-compatible value.
        field: Parent field name used to normalize explicitly set-like lists.

    Returns:
        Canonical JSON-compatible data.

    Raises:
        TypeError: If a value cannot be represented by the canonical format.
        ValueError: If a floating-point value is not finite.

    """
    if isinstance(value, Manifest):
        return canonical_data(value.to_dict(), field=field)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return canonical_data(dataclasses.asdict(value), field=field)
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, Any], value)
        keys = list(mapping)
        if not all(isinstance(key, str) for key in keys):
            raise TypeError("Canonical mappings require string keys")
        string_keys = cast(list[str], keys)
        result: dict[str, Any] = {}
        for key in sorted(string_keys):
            result[key] = canonical_data(mapping[key], field=key)
        return result
    if isinstance(value, Set) and not isinstance(value, (str, bytes)):
        normalized = [canonical_data(item) for item in cast(Set[Any], value)]
        return sorted(normalized, key=canonical_json)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        normalized = [
            canonical_data(item) for item in cast(Sequence[Any], value)
        ]
        if field in _SET_LIKE_KEYS:
            return sorted(normalized, key=canonical_json)
        return normalized
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Canonical JSON does not permit non-finite numbers")
    if value is None or isinstance(value, (int, float, bool)):
        return value
    raise TypeError(f"Unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize a value as canonical JSON text."""
    return json.dumps(
        canonical_data(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_bytes(value: Any) -> bytes:
    """Serialize a value as canonical UTF-8 JSON bytes."""
    return canonical_json(value).encode("utf-8")


def content_hash(value: Any) -> str:
    """Return the lowercase SHA-256 of canonical JSON bytes."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    """Return the SHA-256 digest of exact file bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
