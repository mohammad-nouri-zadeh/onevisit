#!/bin/sh
# Batteria completa: formattazione, lint, tipi, test con copertura.
# Gira nel container di test (`make test`) e in CI.
set -eu

echo "==> ruff format --check"
uv run ruff format --check .

echo "==> ruff check"
uv run ruff check .

echo "==> mypy (strict)"
uv run mypy apps libs conftest.py

echo "==> pytest (unit e integrazione; esclusi llm ed e2e)"
uv run pytest -m "not llm and not e2e" \
  --cov --cov-report=term-missing \
  --cov-fail-under="${COVERAGE_MIN:-70}"
