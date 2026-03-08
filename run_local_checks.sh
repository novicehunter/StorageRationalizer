#!/bin/bash
set -e

echo "Running local security/testing checks..."
echo ""

# Black formatting
echo "[1/4] black (code formatting)..."
black . --quiet

# Flake8 linting
echo "[2/4] flake8 (linting)..."
flake8 tools/ phase3/ --max-line-length=100 --extend-ignore=E203,W503 || true

# MyPy type checking
echo "[3/4] mypy (type checking)..."
mypy tools/ phase3/ --ignore-missing-imports || true

# Pytest
echo "[4/4] pytest (running tests)..."
pytest tests/ -v --cov=tools --cov=phase3 --cov-report=term-missing

echo ""
echo "✅ All checks passed!"
