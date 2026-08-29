"""Command-line adapter for ASC OS services."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from asc_os.api import validate_project
from asc_os.version import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the deterministic command parser."""
    parser = argparse.ArgumentParser(
        prog="asc-os",
        description="Local-first research state and compatibility tools.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate a project.")
    validate.add_argument("path", nargs="?", default=".")
    validate.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a stable exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        report = validate_project(args.path)
        if args.json:
            print(
                json.dumps(
                    report.to_dict(), sort_keys=True, separators=(",", ":")
                )
            )
        elif report.valid:
            print(
                f"valid: {report.manifest_count} manifests in "
                f"{report.project_root}"
            )
        else:
            for error in report.errors:
                print(f"{error['code']}: {error['message']}", file=sys.stderr)
        return 0 if report.valid else 4
    return 12
