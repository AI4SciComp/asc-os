"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def minimal_project(tmp_path: Path) -> Path:
    """Create a valid minimal research project."""
    research = tmp_path / "research"
    (research / "contexts" / "root").mkdir(parents=True)
    (research / "project.yaml").write_text(
        """\
api_version: ai4scicomp.research/v1
kind: ResearchProject
metadata:
  id: PRJ-0001
  title: Minimal project
  status: active
  labels: []
spec:
  repository: AI4SciComp/example
  root_context: CTX-ROOT
  notation: research/notation.yaml
  assumptions: research/assumptions.yaml
  required_covers: []
  artifact_targets: []
  policies:
    verified_claim_requires_evidence: true
    generated_outputs_are_authoritative: false
""",
        encoding="utf-8",
    )
    (research / "notation.yaml").write_text("symbols: {}\n", encoding="utf-8")
    (research / "assumptions.yaml").write_text(
        "assumptions: []\n", encoding="utf-8"
    )
    (research / "contexts" / "root" / "context.yaml").write_text(
        """\
api_version: ai4scicomp.research/v1
kind: ResearchContext
metadata:
  id: CTX-ROOT
  title: Root context
  status: active
  labels: []
spec:
  parent: null
  question: What is the bounded question?
  inputs:
    contexts: []
    files: [research/notation.yaml, research/assumptions.yaml]
  outputs: []
  acceptance: [the declared state validates]
  excluded_scope: [external execution]
""",
        encoding="utf-8",
    )
    return tmp_path
