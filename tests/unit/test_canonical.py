"""Tests for deterministic canonical data and content hashes."""

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from asc_os.canonical import canonical_data, canonical_json, content_hash
from asc_os.manifest import Manifest, Metadata


def test_canonical_golden_vector() -> None:
    value = {"b": [2, 3], "a": 1}
    assert canonical_json(value) == '{"a":1,"b":[2,3]}'
    assert content_hash(value) == (
        "efbd0040190fb0871831e606c581f8a66db79d8e2bb836745a70051306956070"
    )


def test_explicit_set_like_fields_are_sorted() -> None:
    left = {"labels": ["zeta", "alpha"], "steps": ["zeta", "alpha"]}
    right = {"labels": ["alpha", "zeta"], "steps": ["zeta", "alpha"]}
    assert content_hash(left) == content_hash(right)
    assert canonical_data(left)["steps"] == ["zeta", "alpha"]


def test_manifest_excludes_noncanonical_source_path() -> None:
    raw: dict[str, object] = {
        "api_version": "ai4scicomp.research/v1",
        "kind": "ResearchContext",
        "metadata": {
            "id": "CTX-ONE",
            "title": "One",
            "status": "draft",
            "labels": [],
        },
        "spec": {"question": "Why?"},
    }
    manifest = Manifest(
        api_version="ai4scicomp.research/v1",
        kind="ResearchContext",
        metadata=Metadata("CTX-ONE", "One", "draft", ()),
        spec={"question": "Why?"},
        path=Path("one.yaml"),
        raw=raw,
    )
    assert canonical_data(manifest) == raw


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_number_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json(value)


def test_nonstring_mapping_key_is_rejected() -> None:
    with pytest.raises(TypeError, match="string keys"):
        canonical_json({1: "value"})


_JSON_SCALARS = st.none() | st.booleans() | st.integers() | st.text()
_JSON_VALUES = st.recursive(
    _JSON_SCALARS,
    lambda children: (
        st.lists(children, max_size=5)
        | st.dictionaries(st.text(), children, max_size=5)
    ),
    max_leaves=20,
)


@given(_JSON_VALUES)
def test_canonicalization_is_idempotent(value: object) -> None:
    first = canonical_json(value)
    second = canonical_json(json.loads(first))
    assert second == first
