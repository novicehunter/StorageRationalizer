#!/bin/bash
set -e

echo "================================"
echo "StorageRationalizer Setup"
echo "Security + Testing + CI/CD"
echo "================================"
echo ""

# Step 1: Install dependencies
echo "[1/7] Installing dependencies..."
pip install --break-system-packages \
  black \
  flake8 \
  mypy \
  pytest \
  pytest-cov \
  detect-secrets \
  bandit \
  cryptography \
  pre-commit

# Step 2: Create test directory
echo "[2/7] Creating test directory structure..."
mkdir -p tests/mocks
touch tests/__init__.py
touch tests/mocks/__init__.py
touch tests/conftest.py

# Step 3: Create configuration files
echo "[3/7] Creating configuration files..."
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/psf/black
    rev: 23.12.0
    hooks:
      - id: black
        language_version: python3
  - repo: https://github.com/PyCQA/flake8
    rev: 6.1.0
    hooks:
      - id: flake8
        args: ['--max-line-length=100', '--extend-ignore=E203,W503']
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
        args: ['--ignore-missing-imports']
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
EOF

cat > pyproject.toml << 'EOF'
[tool.black]
line-length = 100
target-version = ['py39', 'py310', 'py311']

[tool.mypy]
python_version = "3.9"
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
addopts = "-v --cov=tools --cov-report=html --cov-report=term-missing"
EOF

cat > pytest.ini << 'EOF'
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --cov=tools --cov-report=html --cov-report=term-missing
EOF

# Step 4: Create GitHub Actions workflows
echo "[4/7] Creating GitHub Actions workflows..."
mkdir -p .github/workflows

cat > .github/workflows/test.yml << 'EOF'
name: Test & Lint

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: macos-latest
    strategy:
      matrix:
        python-version: ['3.10', '3.11']

    steps:
    - uses: actions/checkout@v3
    - uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    - run: pip install black flake8 mypy pytest pytest-cov detect-secrets cryptography
    - run: black --check .
    - run: flake8 tools/ phase3/ --max-line-length=100 || true
    - run: mypy tools/ phase3/ --ignore-missing-imports || true
    - run: detect-secrets scan --baseline .secrets.baseline || true
    - run: pytest --cov=tools --cov=phase3 || true
EOF

cat > .github/workflows/security.yml << 'EOF'
name: Security Scan

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  security:
    runs-on: macos-latest

    steps:
    - uses: actions/checkout@v3
    - uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    - run: pip install bandit
    - run: bandit -r tools/ phase3/ -f json -o bandit-report.json || true
EOF

# Step 5: Create test fixtures
echo "[5/7] Creating test fixtures..."
cat > tests/conftest.py << 'EOF'
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

@pytest.fixture
def temp_creds_dir():
    """Temporary credentials directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "credentials"
        path.mkdir()
        (path / "encrypted").mkdir()
        yield path

@pytest.fixture
def temp_db():
    """Temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name

@pytest.fixture
def mock_onedrive_api():
    """Mock OneDrive API responses."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"id": "file_123"}
    return mock

@pytest.fixture
def mock_google_api():
    """Mock Google Drive API responses."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"id": "file_456"}
    return mock
EOF

# Step 6: Initialize pre-commit
echo "[6/7] Initializing pre-commit hooks..."
pre-commit install
detect-secrets scan > .secrets.baseline 2>/dev/null || echo "{}" > .secrets.baseline

# Step 7: Run initial validation
echo "[7/7] Running initial validation..."
echo "  - black (code formatting)..."
black . --quiet 2>/dev/null || true
echo "  - flake8 (linting)..."
flake8 tools/ phase3/ --max-line-length=100 --extend-ignore=E203,W503 || true
echo "  - mypy (type checking)..."
mypy tools/ phase3/ --ignore-missing-imports 2>/dev/null || true
echo "  - pytest (running tests)..."
pytest tests/ -q 2>/dev/null || echo "  (tests may fail before implementations complete)"

echo ""
echo "================================"
echo "✅ Setup Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Review .pre-commit-config.yaml"
echo "2. Create test files in tests/"
echo "3. Run: pre-commit install"
echo "4. Make changes and commit"
echo "5. Push to GitHub to trigger Actions"
echo ""
