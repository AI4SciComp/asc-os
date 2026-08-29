"""Verify deterministic pilot output and second-run idempotency."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from asc_os.context import build_context


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    """Build the pilot twice and compare every committed golden digest."""
    repository = Path(__file__).resolve().parents[1]
    source = repository / "examples" / "ap-kinetic-study"
    expected = cast(
        dict[str, Any],
        json.loads(
            (source / "expected" / "golden-hashes.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    with tempfile.TemporaryDirectory(prefix="asc-os-golden-") as temporary:
        project = Path(temporary) / source.name
        shutil.copytree(source, project)
        first = build_context(project, "CTX-ORBIT", harness="codex")
        if first.source_hash != expected["source_sha256"]:
            raise SystemExit("pilot source hash differs from the golden value")
        files = cast(dict[str, str], expected["files"])
        actual = {name: _sha256(project / name) for name in files}
        if actual != files:
            raise SystemExit("generated pilot files differ from golden values")
        second = build_context(project, "CTX-ORBIT", harness="codex")
        if not second.plan.is_noop:
            raise SystemExit("second context build was not an explicit no-op")
    print("pilot golden output and second-run idempotency: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
