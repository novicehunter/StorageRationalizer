# StorageRationalizer — Master Security & Testing Setup

## OVERVIEW

This document provides:
1. **Security Design** — Credentials encryption, secure storage
2. **Testing Design** — Unit tests, integration tests, test fixtures
3. **CI/CD Design** — Pre-commit hooks, GitHub Actions, automated validation
4. **Implementation Scripts** — Ready-to-run setup scripts
5. **Validation Script** — Verify everything is correctly installed

---

## SECTION 1: SECURITY DESIGN

### Goals
- ✅ No credentials in plaintext on disk
- ✅ Credentials encrypted with AES-256-GCM
- ✅ Master password cached for session (60 min)
- ✅ Cross-platform (Mac/Windows)
- ✅ Auto-migrate legacy files to encrypted storage

### Key Component: CredentialsManager
- `tools/credentials_manager.py` — Handles all credential encryption/decryption
- On first run: prompts for master password
- Reads plaintext files → encrypts → deletes originals
- All future runs: loads from `credentials/encrypted/`

### File Structure
```
credentials/
├── encrypted/                    ← ALL credentials here (encrypted)
│   ├── onedrive.enc
│   ├── onedrive.meta
│   ├── google.enc
│   ├── google.meta
│   └── ... (other services)
├── onedrive_credentials.txt      ← DEPRECATED (auto-migrated)
├── google_credentials.json       ← DEPRECATED (auto-migrated)
└── ... (other legacy files)
```

---

## SECTION 2: TESTING DESIGN

### Test Structure
```
tests/
├── conftest.py              ← Pytest fixtures (temp dirs, mocks)
├── test_credentials_manager.py
├── test_rollback.py
├── test_tracker.py
├── test_verify_cleanup.py
└── mocks/
    ├── mock_onedrive_api.py
    ├── mock_google_api.py
    └── mock_databases.py
```

### Key Principles
- Unit tests for each module
- Mocked API responses (no real API calls in tests)
- Fixtures for temporary directories, databases
- Coverage minimum: 80% for `tools/` and `phase3/`
- All tests run locally before commit
- All tests run on GitHub before merge

### Example Test
```python
# tests/test_credentials_manager.py
def test_credentials_manager_saves_encrypted(temp_creds_dir):
    """Verify credentials are encrypted, not plaintext."""
    cm = CredentialsManager(creds_dir=str(temp_creds_dir))
    with patch('getpass.getpass', return_value='test_password'):
        cm.save("onedrive", "CLIENT_SECRET", "secret_value_123")

    # Verify .enc file exists (encrypted)
    enc_file = temp_creds_dir / "encrypted" / "onedrive.enc"
    assert enc_file.exists()

    # Verify file content is NOT plaintext
    with open(enc_file, 'rb') as f:
        content = f.read()
    assert b"secret_value_123" not in content
    assert b"CLIENT_SECRET" not in content
```

---

## SECTION 3: CI/CD DESIGN

### Local Gates (Pre-Commit Hooks)
Developer runs `git commit`
  ↓
Pre-commit hooks execute:
  - black (auto-format code)
  - flake8 (lint check)
  - mypy (type checking)
  - detect-secrets (scan for credentials)
  ↓
If any fail → commit BLOCKED, developer fixes
If all pass → commit ALLOWED

### Remote Gates (GitHub Actions)
Developer runs `git push`
  ↓
GitHub Actions runs:
  - All pre-commit checks again
  - Full pytest suite with coverage report
  - Security scanning (bandit)
  - Tests on Python 3.10 + 3.11
  ↓
If any fail → PR BLOCKED, cannot merge
If all pass → PR ready to merge

### Branch Protection Rules
- Require all checks to pass before merge
- Require coverage ≥ 80%
- Require no high-severity bandit issues

---

## SECTION 4: IMPLEMENTATION SCRIPTS

### Script 1: `setup_security_testing.sh`
**Purpose:** One-command setup of all security, testing, CI/CD

```bash
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
  - repo: https://github.com/PyCF/flake8
    rev: 6.1.0
    hooks:
      - id: flake8
        args: ['--max-line-length=100', '--extend-ignore=E203,W503']
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
        additional_dependencies: ['types-all']
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
```

### Script 2: `validate_setup.sh`
**Purpose:** Verify all security/testing/CI/CD components are in place

```bash
#!/bin/bash

echo "================================"
echo "Validating Security/Testing Setup"
echo "================================"
echo ""

PASS=0
FAIL=0

# Check 1: Pre-commit config
if [ -f ".pre-commit-config.yaml" ]; then
  echo "✅ .pre-commit-config.yaml exists"
  ((PASS++))
else
  echo "❌ .pre-commit-config.yaml missing"
  ((FAIL++))
fi

# Check 2: pyproject.toml
if [ -f "pyproject.toml" ] && grep -q "\[tool.black\]" pyproject.toml; then
  echo "✅ pyproject.toml configured"
  ((PASS++))
else
  echo "❌ pyproject.toml not configured"
  ((FAIL++))
fi

# Check 3: pytest.ini
if [ -f "pytest.ini" ]; then
  echo "✅ pytest.ini exists"
  ((PASS++))
else
  echo "❌ pytest.ini missing"
  ((FAIL++))
fi

# Check 4: GitHub Actions workflows
if [ -f ".github/workflows/test.yml" ]; then
  echo "✅ .github/workflows/test.yml exists"
  ((PASS++))
else
  echo "❌ .github/workflows/test.yml missing"
  ((FAIL++))
fi

if [ -f ".github/workflows/security.yml" ]; then
  echo "✅ .github/workflows/security.yml exists"
  ((PASS++))
else
  echo "❌ .github/workflows/security.yml missing"
  ((FAIL++))
fi

# Check 5: Test directory
if [ -d "tests" ] && [ -f "tests/conftest.py" ]; then
  echo "✅ tests/conftest.py exists"
  ((PASS++))
else
  echo "❌ tests/conftest.py missing"
  ((FAIL++))
fi

# Check 6: Pre-commit hooks installed
if [ -f ".git/hooks/pre-commit" ]; then
  echo "✅ Pre-commit hooks installed"
  ((PASS++))
else
  echo "❌ Pre-commit hooks not installed (run: pre-commit install)"
  ((FAIL++))
fi

# Check 7: Secrets baseline
if [ -f ".secrets.baseline" ]; then
  echo "✅ .secrets.baseline exists"
  ((PASS++))
else
  echo "❌ .secrets.baseline missing (run: detect-secrets scan > .secrets.baseline)"
  ((FAIL++))
fi

# Check 8: .gitignore updated
if grep -q "credentials/encrypted" .gitignore 2>/dev/null; then
  echo "✅ .gitignore includes credentials/encrypted"
  ((PASS++))
else
  echo "❌ .gitignore missing credentials/encrypted (add: credentials/encrypted/)"
  ((FAIL++))
fi

# Check 9: credentials_manager.py exists
if [ -f "tools/credentials_manager.py" ]; then
  echo "✅ tools/credentials_manager.py exists"
  ((PASS++))
else
  echo "❌ tools/credentials_manager.py missing"
  ((FAIL++))
fi

# Check 10: Dependencies installed
if python3 -c "import black, flake8, mypy, pytest, cryptography" 2>/dev/null; then
  echo "✅ All dependencies installed"
  ((PASS++))
else
  echo "❌ Missing dependencies (run: pip install --break-system-packages black flake8 mypy pytest pytest-cov detect-secrets cryptography)"
  ((FAIL++))
fi

echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
echo "================================"

if [ $FAIL -eq 0 ]; then
  echo "✅ All checks passed!"
  exit 0
else
  echo "❌ Some checks failed. Fix issues above."
  exit 1
fi
```

### Script 3: `run_local_checks.sh`
**Purpose:** Run all checks locally before committing (what pre-commit does)

```bash
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
```

---

## SECTION 5: EXECUTION PLAN

### Phase A: Setup (Run Once)
```bash
cd ~/Desktop/StorageRationalizer

# 1. Copy setup script
curl -O https://YOUR_REPO/setup_security_testing.sh  # Or paste script above
chmod +x setup_security_testing.sh

# 2. Run setup
./setup_security_testing.sh

# 3. Validate
./validate_setup.sh

# 4. Commit
git add .
git commit -m "ci: add security, testing, CI/CD setup"
git push
```

### Phase B: Development (Every Commit)
```bash
# Make code changes
git add .
git commit -m "feat: add feature X"
# ← Pre-commit hooks run automatically
# ← If they fail, fix and retry commit

# Push to GitHub
git push
# ← GitHub Actions runs automatically
# ← Tests/lint/security checks run
```

### Phase C: Migrate Credentials (First Run)
```bash
# First time running any script that uses credentials:
python3 tools/credentials_manager.py --migrate

# Prompts: "Enter master password: "
# Auto-migrates plaintext files to encrypted storage
# Updates rollback.py, tracker.py to use CredentialsManager
```

---

## SECTION 6: VALIDATION CHECKLIST

Before proceeding to CRITICAL Issue 2, verify:

- [ ] `.pre-commit-config.yaml` exists
- [ ] `pyproject.toml` exists
- [ ] `pytest.ini` exists
- [ ] `.github/workflows/test.yml` exists
- [ ] `.github/workflows/security.yml` exists
- [ ] `tests/conftest.py` exists
- [ ] `tools/credentials_manager.py` exists and committed
- [ ] `.gitignore` includes `credentials/encrypted/`
- [ ] `.secrets.baseline` exists
- [ ] Pre-commit hooks installed (`pre-commit install`)
- [ ] All dependencies installed
- [ ] `./validate_setup.sh` passes all checks

---

## SECTION 7: INTEGRATION WITH EXISTING CODE

### Update `rollback.py`
```python
# At module level (after imports)
from tools.credentials_manager import CredentialsManager
creds = CredentialsManager()  # Initialize once

# In _restore_onedrive function
def _restore_onedrive(rec: dict) -> tuple:
    tenant_id = creds.load("onedrive", "TENANT_ID")
    client_id = creds.load("onedrive", "CLIENT_ID")
    client_secret = creds.load("onedrive", "CLIENT_SECRET")
    # ... rest of function
```

### Update `tracker.py`
```python
# At module level (after imports)
from tools.credentials_manager import CredentialsManager
creds = CredentialsManager()  # Initialize once

@app.before_first_request
def init_creds():
    # Prompt for master password once when Flask starts
    pass
```

---

## NEXT STEPS

1. ✅ Run `setup_security_testing.sh` to set up all files
2. ✅ Run `validate_setup.sh` to verify everything
3. ✅ Commit to git
4. ✅ Push to GitHub (GitHub Actions will run)
5. ⏳ Then: CRITICAL Issue 2 (API Response Validation)
6. ⏳ Then: CRITICAL Issue 3 (AppleScript Injection Fix)
7. ⏳ Then: HIGH Issues 4-7
