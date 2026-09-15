"""Enforce the repository's separate branch coverage threshold."""

from pathlib import Path
from xml.etree import ElementTree

_MINIMUM_PERCENT = 90


def main() -> int:
    """Check the local coverage.py XML report produced by make test."""
    report = Path(__file__).resolve().parents[1] / "coverage.xml"
    root = ElementTree.parse(report).getroot()  # noqa: S314 - local test output.
    covered = int(root.attrib["branches-covered"])
    total = int(root.attrib["branches-valid"])
    if total <= 0 or covered * 100 < _MINIMUM_PERCENT * total:
        raise SystemExit(
            f"Branch coverage {covered}/{total} is below {_MINIMUM_PERCENT}%"
        )
    print(f"Branch coverage: {covered / total:.2%} (minimum 90%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
