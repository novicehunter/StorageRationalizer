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
