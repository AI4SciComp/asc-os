"""Exercise documented quickstart operations in an isolated project."""

from __future__ import annotations

import tempfile
from pathlib import Path

from asc_os.api import validate_project
from asc_os.context import build_context
from asc_os.scaffold import init_project


def main() -> int:
    """Run the quickstart without modifying the checkout."""
    with tempfile.TemporaryDirectory(prefix="asc-os-quickstart-") as temporary:
        project = Path(temporary) / "demo"
        first = init_project(project, dry_run=True)
        if first.is_noop or project.exists():
            raise SystemExit("initial dry-run did not remain mutation-free")
        init_project(project)
        if not validate_project(project).valid:
            raise SystemExit("quickstart project failed validation")
        build_context(project, "CTX-ROOT", harness="codex")
        second = build_context(project, "CTX-ROOT", harness="codex")
        if not second.plan.is_noop:
            raise SystemExit("quickstart second build was not a no-op")
    print("isolated quickstart: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
