.PHONY: sync format format-check lint typecheck test security-test examples docs linkcheck build check

sync:
	uv sync --frozen --all-groups --all-extras

format:
	uv run ruff format .
	uv run ruff check --fix .

format-check:
	uv run ruff format --check .

lint:
	uv run ruff check .
	uv run pylint src/asc_os scripts

typecheck:
	uv run pyright

test:
	uv run pytest --cov=asc_os --cov-branch --cov-report=term-missing --cov-report=xml

security-test:
	uv run pytest tests/security tests/unit/test_manifest.py tests/unit/test_paths.py tests/unit/test_storage.py tests/integration/test_mcp.py tests/integration/test_provenance.py tests/integration/test_skills.py tests/integration/test_verification.py
	uv export --frozen --all-groups --all-extras --no-emit-project --format requirements-txt | uv run pip-audit --strict -r /dev/stdin

examples:
	uv run asc-os validate examples/ap-kinetic-study
	uv run python scripts/check_generated.py

docs:
	uv run sphinx-build -W --keep-going -b html docs docs/_build/html
	uv run sphinx-build -W --keep-going -b doctest docs docs/_build/doctest
	uv run python scripts/check_quickstart.py

linkcheck:
	uv run sphinx-build -W --keep-going -b linkcheck docs docs/_build/linkcheck

build:
	uv run python -m build
	uv run python -m twine check dist/*

check:
	uv run python scripts/check_repository.py
	uv run python scripts/check_generated.py
	git diff --check
