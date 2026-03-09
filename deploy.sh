#!/usr/bin/env bash
# StorageRationalizer — Deployment / Setup Script (STUB)
# See: docs/DEPLOYMENT_GUIDE.md
# Status: STUB — test before using in production

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
PYTHON="python3"

echo "=== StorageRationalizer Setup ==="
echo "Repo: $REPO_DIR"
echo ""

# ── 1. Python version check ────────────────────────────────────────────────
PY_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "[1/6] Python version: $PY_VERSION"
if ! $PYTHON -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"; then
    echo "ERROR: Python 3.11+ required. Got $PY_VERSION"
    exit 1
fi

# ── 2. Virtual environment ─────────────────────────────────────────────────
echo "[2/6] Setting up virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR"
    echo "  Created: $VENV_DIR"
else
    echo "  Already exists: $VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# ── 3. Install dependencies ────────────────────────────────────────────────
echo "[3/6] Installing pinned dependencies..."
pip install --quiet -r "$REPO_DIR/requirements.txt"
echo "  Done."

# ── 4. Pre-commit hooks ────────────────────────────────────────────────────
echo "[4/6] Installing pre-commit hooks..."
pre-commit install
echo "  Done."

# ── 5. Run tests ───────────────────────────────────────────────────────────
echo "[5/6] Running test suite..."
pytest tests/ -q --tb=short
echo "  Done."

# ── 6. Verify security fixes ───────────────────────────────────────────────
echo "[6/6] Verifying security fixes..."
bash "$REPO_DIR/verify_issues.sh"

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Store credentials: python3 tools/credentials_manager.py save <service> <key> <value>"
echo "  2. Dry run: python3 phase1/scanner.py --dry-run"
echo "  3. See docs/DEPLOYMENT_GUIDE.md for full instructions"
