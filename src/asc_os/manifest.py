"""Safe manifest loading, typed records, and reference indexing."""

from __future__ import annotations

import json
import os
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import jsonschema
import yaml
from referencing import Registry, Resource
from yaml import events

from asc_os.errors import (
    ErrorDetail,
    ExitCode,
    ManifestError,
    ReferenceIntegrityError,
)
from asc_os.paths import confined_path, find_project_root, relative_posix

API_VERSION = "ai4scicomp.research/v1"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_YAML_DEPTH = 64
_CONTROL_BOUNDARY = 32

KIND_SCHEMA: Mapping[str, str] = {
    "ResearchProject": "project.schema.json",
    "ResearchContext": "context.schema.json",
    "ResearchCover": "cover.schema.json",
    "ResearchOverlap": "overlap.schema.json",
    "ResearchClaim": "claim.schema.json",
    "ResearchDecision": "decision.schema.json",
    "ResearchEvidence": "evidence.schema.json",
    "ResearchArtifact": "artifact.schema.json",
    "ResearchSkill": "skill.schema.json",
    "ResearchRun": "run.schema.json",
}

KIND_PREFIX: Mapping[str, str] = {
    "ResearchProject": "PRJ-",
    "ResearchContext": "CTX-",
    "ResearchCover": "COV-",
    "ResearchOverlap": "OVL-",
    "ResearchClaim": "CLM-",
    "ResearchDecision": "DEC-",
    "ResearchEvidence": "EVD-",
    "ResearchArtifact": "ART-",
    "ResearchSkill": "SKL-",
    "ResearchRun": "RUN-",
}


class _StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects aliases, duplicates, and deep inputs."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._asc_depth = 0

    def compose_node(self, parent: Any, index: Any) -> yaml.Node:
        if self.check_event(events.AliasEvent):
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "YAML aliases are disabled",
                None,
            )
        self._asc_depth += 1
        if self._asc_depth > MAX_YAML_DEPTH:
            raise yaml.constructor.ConstructorError(
                None,
                None,
                f"YAML nesting exceeds {MAX_YAML_DEPTH}",
                None,
            )
        try:
            composed = super().compose_node(parent, index)
            if composed is None:
                raise yaml.constructor.ConstructorError(
                    None,
                    None,
                    "YAML node composition failed",
                    None,
                )
            return composed
        finally:
            self._asc_depth -= 1

    def construct_mapping(
        self,
        node: yaml.MappingNode,
        deep: bool = False,
    ) -> dict[Hashable, Any]:
        self.flatten_mapping(node)
        result: dict[Hashable, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(  # pyright: ignore[reportUnknownMemberType]
                key_node, deep=deep
            )
            if not isinstance(key, str):
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "manifest mapping keys must be strings",
                    key_node.start_mark,
                )
            if key in result:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key: {key}",
                    key_node.start_mark,
                )
            result[key] = self.construct_object(  # pyright: ignore[reportUnknownMemberType]
                value_node, deep=deep
            )
        return result


@dataclass(frozen=True, slots=True)
class Metadata:
    """Common immutable manifest metadata."""

    id: str
    title: str
    status: str
    labels: tuple[str, ...]
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class Manifest:
    """A schema-validated research manifest."""

    api_version: str
    kind: str
    metadata: Metadata
    spec: Mapping[str, Any]
    path: Path
    raw: Mapping[str, Any]

    @property
    def id(self) -> str:
        """Return the immutable record identifier."""
        return self.metadata.id

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible copy of the validated manifest."""
        return cast(dict[str, Any], json.loads(json.dumps(self.raw)))


@dataclass(frozen=True, slots=True)
class ProjectState:
    """Loaded authored state for one research project."""

    root: Path
    project: Manifest
    manifests: tuple[Manifest, ...]
    index: Mapping[str, Manifest]
    notation: Mapping[str, Any]
    assumptions: Mapping[str, Any]

    def by_kind(self, kind: str) -> tuple[Manifest, ...]:
        """Return manifests of ``kind`` in stable identifier order."""
        return tuple(item for item in self.manifests if item.kind == kind)

    def require(self, record_id: str, kind: str | None = None) -> Manifest:
        """Resolve an ID and optionally enforce its kind."""
        item = self.index.get(record_id)
        if item is None or (kind is not None and item.kind != kind):
            raise _reference_error(
                "unresolved_reference",
                f"Reference {record_id!r} does not resolve"
                + (f" as {kind}." if kind else "."),
                self.project.path,
            )
        return item


class SchemaCatalog:
    """Load and validate the bundled v1 JSON Schemas."""

    def __init__(self, schema_root: Path | None = None) -> None:
        """Load schemas from ``schema_root`` or the bundled catalog."""
        self.root = schema_root or _default_schema_root()
        self._schemas: dict[str, Mapping[str, Any]] = {}
        for path in sorted(self.root.glob("*.schema.json")):
            with path.open(encoding="utf-8") as stream:
                schema = json.load(stream)
            self._schemas[path.name] = cast(Mapping[str, Any], schema)
        common = self._schemas.get("common.schema.json")
        if common is None:
            raise RuntimeError("Bundled common schema is missing")
        registry: Registry[Any] = Registry()
        for schema in self._schemas.values():
            schema_id = schema.get("$id")
            if isinstance(schema_id, str):
                registry = registry.with_resource(
                    schema_id,
                    Resource.from_contents(schema),
                )
        self._registry = registry

    def schema(self, name: str) -> Mapping[str, Any]:
        """Return a named schema or raise a stable schema error."""
        try:
            return self._schemas[name]
        except KeyError as error:
            raise ManifestError(
                ErrorDetail(
                    code="schema_not_found",
                    message=f"Schema {name!r} is not bundled.",
                    hint="Use a schema from the supported v1 catalog.",
                ),
                ExitCode.SCHEMA_INVALID,
            ) from error

    def validate(self, document: Mapping[str, Any], path: Path) -> None:
        """Validate a manifest against its exact declared kind/version."""
        version = document.get("api_version")
        if version != API_VERSION:
            raise ManifestError(
                ErrorDetail(
                    code="unsupported_api_version",
                    message=f"Unsupported api_version {version!r}.",
                    path=os.fspath(path),
                    hint=f"Use {API_VERSION!r}.",
                ),
                ExitCode.UNSUPPORTED_API,
            )
        kind = document.get("kind")
        schema_name = KIND_SCHEMA.get(cast(str, kind))
        if schema_name is None:
            raise ManifestError(
                ErrorDetail(
                    code="unknown_manifest_kind",
                    message=f"Unsupported manifest kind {kind!r}.",
                    path=os.fspath(path),
                    hint="Use a kind from the v1 schema catalog.",
                ),
                ExitCode.SCHEMA_INVALID,
            )
        schema = self.schema(schema_name)
        validator = jsonschema.Draft202012Validator(
            schema,
            registry=self._registry,
            format_checker=jsonschema.FormatChecker(),
        )
        errors = sorted(
            validator.iter_errors(  # pyright: ignore[reportUnknownMemberType]
                document
            ),
            key=_error_key,
        )
        if errors:
            first = errors[0]
            location = "/" + "/".join(str(part) for part in first.path)
            raise ManifestError(
                ErrorDetail(
                    code="schema_validation_failed",
                    message=f"{location}: {first.message}",
                    path=os.fspath(path),
                    hint="Correct the authored manifest and validate again.",
                ),
                ExitCode.SCHEMA_INVALID,
            )


def load_yaml(path: Path, *, max_bytes: int = MAX_MANIFEST_BYTES) -> Any:
    """Load safe YAML with explicit byte, alias, duplicate, and depth limits."""
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ManifestError(
            ErrorDetail(
                code="manifest_read_failed",
                message=str(error),
                path=os.fspath(path),
                hint="Check that the file is readable.",
            ),
            ExitCode.SCHEMA_INVALID,
        ) from error
    if len(payload) > max_bytes:
        raise ManifestError(
            ErrorDetail(
                code="manifest_too_large",
                message=f"Manifest exceeds the {max_bytes}-byte limit.",
                path=os.fspath(path),
                hint="Split large evidence into external hashed artifacts.",
            ),
            ExitCode.SCHEMA_INVALID,
        )
    try:
        text = payload.decode("utf-8", errors="strict")
        _reject_control_characters(text)
        # The loader inherits SafeLoader and exposes no unsafe constructors.
        return yaml.load(text, Loader=_StrictSafeLoader)  # noqa: S506
    except (UnicodeDecodeError, ValueError, yaml.YAMLError) as error:
        raise ManifestError(
            ErrorDetail(
                code="unsafe_or_invalid_yaml",
                message=str(error),
                path=os.fspath(path),
                hint=(
                    "Use UTF-8 safe YAML without aliases, tags, or duplicates."
                ),
            ),
            ExitCode.SCHEMA_INVALID,
        ) from error


def _reject_control_characters(text: str) -> None:
    """Reject terminal and record controls while retaining YAML whitespace."""
    if any(
        ord(character) < _CONTROL_BOUNDARY and character not in "\t\n\r"
        for character in text
    ):
        raise ValueError("YAML contains a disallowed control character")


def load_manifest(path: Path, catalog: SchemaCatalog | None = None) -> Manifest:
    """Safely load, validate, and type one manifest."""
    document = load_yaml(path)
    if not isinstance(document, Mapping):
        raise ManifestError(
            ErrorDetail(
                code="manifest_not_mapping",
                message="A manifest must be a YAML mapping.",
                path=os.fspath(path),
                hint="Use the api_version/kind/metadata/spec envelope.",
            ),
            ExitCode.SCHEMA_INVALID,
        )
    typed = cast(Mapping[str, Any], document)
    (catalog or SchemaCatalog()).validate(typed, path)
    kind = cast(str, typed["kind"])
    raw_metadata = cast(Mapping[str, Any], typed["metadata"])
    record_id = cast(str, raw_metadata["id"])
    if not record_id.startswith(KIND_PREFIX[kind]):
        raise ManifestError(
            ErrorDetail(
                code="invalid_id_prefix",
                message=f"{record_id!r} does not use {KIND_PREFIX[kind]!r}.",
                path=os.fspath(path),
                hint="Use the stable prefix assigned to this manifest kind.",
            ),
            ExitCode.SCHEMA_INVALID,
        )
    metadata = Metadata(
        id=record_id,
        title=cast(str, raw_metadata["title"]),
        status=cast(str, raw_metadata["status"]),
        labels=tuple(cast(Iterable[str], raw_metadata.get("labels", ()))),
        created_at=cast(str | None, raw_metadata.get("created_at")),
        updated_at=cast(str | None, raw_metadata.get("updated_at")),
    )
    return Manifest(
        api_version=API_VERSION,
        kind=kind,
        metadata=metadata,
        spec=cast(Mapping[str, Any], typed["spec"]),
        path=path,
        raw=typed,
    )


def load_project_state(path: str | Path = ".") -> ProjectState:
    """Load every canonical manifest and validate reference integrity."""
    root = find_project_root(path)
    catalog = SchemaCatalog()
    paths = _manifest_paths(root)
    manifests = tuple(load_manifest(item, catalog) for item in paths)
    index: dict[str, Manifest] = {}
    for manifest in manifests:
        previous = index.get(manifest.id)
        if previous is not None:
            raise _reference_error(
                "duplicate_id",
                f"Duplicate ID {manifest.id!r} in "
                f"{relative_posix(root, previous.path)!r} and "
                f"{relative_posix(root, manifest.path)!r}.",
                manifest.path,
            )
        index[manifest.id] = manifest
    project_path = root / "research" / "project.yaml"
    project = next(item for item in manifests if item.path == project_path)
    notation_path = confined_path(
        root, cast(str, project.spec["notation"]), must_exist=True
    )
    assumptions_path = confined_path(
        root,
        cast(str, project.spec["assumptions"]),
        must_exist=True,
    )
    notation = _require_mapping(load_yaml(notation_path), notation_path)
    assumptions = _require_mapping(
        load_yaml(assumptions_path), assumptions_path
    )
    state = ProjectState(
        root=root,
        project=project,
        manifests=tuple(
            sorted(manifests, key=lambda item: (item.kind, item.id))
        ),
        index=index,
        notation=notation,
        assumptions=assumptions,
    )
    validate_references(state)
    return state


def validate_references(state: ProjectState) -> None:
    """Validate typed references and forbidden dependency cycles."""
    project = state.project
    state.require(cast(str, project.spec["root_context"]), "ResearchContext")
    _require_many(state, project, "required_covers", "ResearchCover")
    _require_many(state, project, "artifact_targets", "ResearchArtifact")
    context_graph: dict[str, list[str]] = {}
    claim_graph: dict[str, list[str]] = {}
    decision_graph: dict[str, list[str]] = {}
    for item in state.manifests:
        spec = item.spec
        if item.kind == "ResearchContext":
            references: list[str] = []
            parent = spec.get("parent")
            if isinstance(parent, str):
                state.require(parent, "ResearchContext")
                references.append(parent)
            inputs = cast(Mapping[str, Any], spec["inputs"])
            for ref in cast(Iterable[str], inputs["contexts"]):
                state.require(ref, "ResearchContext")
                references.append(ref)
            context_graph[item.id] = references
        elif item.kind == "ResearchCover":
            state.require(cast(str, spec["target"]), "ResearchContext")
            _require_many(state, item, "members", "ResearchContext")
            _require_many(
                state,
                item,
                "required_overlaps",
                "ResearchOverlap",
            )
            requirements = cast(
                Mapping[str, Iterable[str]], spec["requirements"]
            )
            for refs in requirements.values():
                for ref in refs:
                    state.require(ref, "ResearchContext")
        elif item.kind == "ResearchOverlap":
            left = cast(str, spec["left"])
            right = cast(str, spec["right"])
            state.require(left, "ResearchContext")
            state.require(right, "ResearchContext")
            if left == right:
                raise _reference_error(
                    "self_overlap",
                    f"Overlap {item.id!r} has identical endpoints.",
                    item.path,
                )
        elif item.kind == "ResearchClaim":
            state.require(cast(str, spec["context"]), "ResearchContext")
            _require_many(state, item, "depends_on", "ResearchClaim")
            _require_many(state, item, "evidence", "ResearchEvidence")
            claim_graph[item.id] = list(cast(Iterable[str], spec["depends_on"]))
        elif item.kind == "ResearchDecision":
            _require_many(state, item, "evidence", "ResearchEvidence")
            _require_many(state, item, "supersedes", "ResearchDecision")
            _require_many(
                state,
                item,
                "affected_contexts",
                "ResearchContext",
            )
            decision_graph[item.id] = list(
                cast(Iterable[str], spec["supersedes"])
            )
        elif item.kind == "ResearchEvidence":
            _require_many(state, item, "supports", "ResearchClaim")
            _require_many(state, item, "contradicts", "ResearchClaim")
            produced = spec.get("produced_by_run")
            if isinstance(produced, str):
                state.require(produced, "ResearchRun")
        elif item.kind == "ResearchArtifact":
            _require_many(state, item, "contexts", "ResearchContext")
            _require_many(state, item, "claims", "ResearchClaim")
        elif item.kind == "ResearchRun":
            context = spec.get("context")
            if isinstance(context, str):
                state.require(context, "ResearchContext")
    _reject_cycles(context_graph, "context_dependency_cycle", state)
    _reject_cycles(claim_graph, "claim_dependency_cycle", state)
    _reject_cycles(decision_graph, "decision_supersession_cycle", state)


def _manifest_paths(root: Path) -> tuple[Path, ...]:
    research = root / "research"
    patterns = (
        "project.yaml",
        "contexts/*/context.yaml",
        "covers/*.yaml",
        "overlaps/*.yaml",
        "claims/*.yaml",
        "decisions/*.yaml",
        "evidence/*/manifest.yaml",
        "artifacts/*.yaml",
        "skills/*.yaml",
        "runs/*/run.yaml",
    )
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(research.glob(pattern))
    return tuple(sorted(paths))


def _require_mapping(value: Any, path: Path) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, Any], value)
    raise ManifestError(
        ErrorDetail(
            code="auxiliary_not_mapping",
            message="Notation and assumptions files must be mappings.",
            path=os.fspath(path),
            hint="Use a YAML mapping with stable keys.",
        ),
        ExitCode.SCHEMA_INVALID,
    )


def _require_many(
    state: ProjectState,
    owner: Manifest,
    field: str,
    kind: str,
) -> None:
    for record_id in cast(Iterable[str], owner.spec.get(field, ())):
        state.require(record_id, kind)


def _reject_cycles(
    graph: Mapping[str, list[str]],
    code: str,
    state: ProjectState,
) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()
    trail: list[str] = []

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            start = trail.index(node)
            cycle = [*trail[start:], node]
            raise _reference_error(
                code,
                "Forbidden reference cycle: " + " -> ".join(cycle),
                state.require(node).path,
            )
        visiting.add(node)
        trail.append(node)
        for child in sorted(graph.get(node, ())):
            visit(child)
        trail.pop()
        visiting.remove(node)
        visited.add(node)

    for record_id in sorted(graph):
        visit(record_id)


def _reference_error(
    code: str, message: str, path: Path
) -> ReferenceIntegrityError:
    return ReferenceIntegrityError(
        ErrorDetail(
            code=code,
            message=message,
            path=os.fspath(path),
            hint="Correct the reference graph and validate again.",
        ),
        ExitCode.REFERENCE_INVALID,
    )


def _error_key(error: jsonschema.ValidationError) -> tuple[str, str]:
    return ("/".join(str(part) for part in error.path), error.message)


def _default_schema_root() -> Path:
    source_root = Path(__file__).resolve().parents[2] / "schemas" / "v1"
    if source_root.is_dir():
        return source_root
    installed = Path(__file__).resolve().parent / "schemas" / "v1"
    if installed.is_dir():
        return installed
    raise RuntimeError("Bundled v1 schemas are missing")
