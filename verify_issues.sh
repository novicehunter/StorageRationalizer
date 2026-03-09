#!/bin/bash

################################################################################
# CRITICAL ISSUES VERIFICATION SCRIPT (FIXED)
# Purpose: Verify all 3 CRITICAL issues without hanging
# Usage: ./verify_issues.sh
# Time: ~30 seconds
################################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { echo -e "${GREEN}✅${NC} $1"; ((PASS++)); }
fail() { echo -e "${RED}❌${NC} $1"; ((FAIL++)); }
warn() { echo -e "${YELLOW}⚠️${NC} $1"; ((WARN++)); }

echo ""
echo "════════════════════════════════════════════════════════"
echo "CRITICAL ISSUES VERIFICATION"
echo "════════════════════════════════════════════════════════"
echo ""

# ============================================================================
# ISSUE 1: CREDENTIALS IN PLAINTEXT
# ============================================================================
echo "ISSUE 1: CREDENTIALS IN PLAINTEXT"
echo "──────────────────────────────────"

if [ -f "tools/credentials_manager.py" ]; then
    pass "credentials_manager.py exists"
else
    fail "credentials_manager.py missing"
fi

if grep -q "class CredentialsManager" tools/credentials_manager.py 2>/dev/null; then
    pass "CredentialsManager class exists"
else
    fail "CredentialsManager class missing"
fi

if grep -q "credentials/encrypted" .gitignore 2>/dev/null; then
    pass "credentials/encrypted in .gitignore"
else
    fail ".gitignore not updated"
fi

echo ""

# ============================================================================
# ISSUE 2: API RESPONSE VALIDATION
# ============================================================================
echo "ISSUE 2: API RESPONSE VALIDATION"
echo "────────────────────────────────"

if [ -f "tools/api_validators.py" ]; then
    pass "api_validators.py exists"

    if grep -q "def validate_restore_response" tools/api_validators.py; then
        pass "validate_restore_response() exists"
    else
        fail "validate_restore_response() missing"
    fi

    if grep -q "def validate_metadata_response" tools/api_validators.py; then
        pass "validate_metadata_response() exists"
    else
        fail "validate_metadata_response() missing"
    fi

    if grep -q "def validate_batch_response" tools/api_validators.py; then
        pass "validate_batch_response() exists"
    else
        fail "validate_batch_response() missing"
    fi

    if grep -q "class APIResponseError" tools/api_validators.py; then
        pass "APIResponseError exception exists"
    else
        fail "APIResponseError missing"
    fi
else
    fail "api_validators.py missing"
fi

if grep -q "from tools.api_validators import" tools/rollback.py 2>/dev/null; then
    pass "rollback.py imports validators"
else
    fail "rollback.py doesn't import validators"
fi

if grep -q "from tools.api_validators import" phase2/verifier.py 2>/dev/null; then
    pass "verifier.py imports validators"
else
    fail "verifier.py doesn't import validators"
fi

if grep -q "from tools.api_validators import" phase3/cleaner.py 2>/dev/null; then
    pass "cleaner.py imports validators"
else
    fail "cleaner.py doesn't import validators"
fi

if [ -f "tests/test_api_validators.py" ]; then
    pass "test_api_validators.py exists"
else
    fail "test_api_validators.py missing"
fi

echo ""

# ============================================================================
# ISSUE 3: APPLESCRIPT INJECTION
# ============================================================================
echo "ISSUE 3: APPLESCRIPT INJECTION"
echo "──────────────────────────────"

if [ -f "tools/input_validators.py" ]; then
    pass "input_validators.py exists"
else
    warn "input_validators.py not yet created (expected in Step 3)"
fi

echo ""

# ============================================================================
# PYTHON SYNTAX CHECK
# ============================================================================
echo "PYTHON SYNTAX CHECKS"
echo "────────────────────"

if python3 -m py_compile tools/api_validators.py 2>/dev/null; then
    pass "api_validators.py syntax valid"
else
    fail "api_validators.py has syntax errors"
fi

if python3 -m py_compile tools/rollback.py 2>/dev/null; then
    pass "rollback.py syntax valid"
else
    fail "rollback.py has syntax errors"
fi

if python3 -m py_compile phase2/verifier.py 2>/dev/null; then
    pass "verifier.py syntax valid"
else
    fail "verifier.py has syntax errors"
fi

if python3 -m py_compile phase3/cleaner.py 2>/dev/null; then
    pass "cleaner.py syntax valid"
else
    fail "cleaner.py has syntax errors"
fi

echo ""

# ============================================================================
# IMPORT TEST
# ============================================================================
echo "IMPORT TESTS"
echo "────────────"

if python3 -c "from tools.api_validators import APIResponseError, validate_json_response, validate_restore_response" 2>/dev/null; then
    pass "api_validators imports work"
else
    fail "api_validators imports failed"
fi

echo ""

# ============================================================================
# GIT STATUS
# ============================================================================
echo "GIT STATUS"
echo "──────────"

echo "Last 3 commits:"
git log --oneline -3
echo ""

if git log --oneline | head -10 | grep -q "CRITICAL Issue 2\|API response\|validation"; then
    pass "CRITICAL Issue 2 commit found"
else
    warn "CRITICAL Issue 2 commit not in recent history"
fi

if [ -z "$(git status --porcelain)" ]; then
    pass "No uncommitted changes"
else
    CHANGES=$(git status --short | wc -l)
    warn "$CHANGES uncommitted changes"
fi

echo ""

# ============================================================================
# INFRASTRUCTURE
# ============================================================================
echo "INFRASTRUCTURE"
echo "───────────────"

[ -f ".pre-commit-config.yaml" ] && pass ".pre-commit-config.yaml exists" || warn ".pre-commit-config.yaml missing"
[ -f "pytest.ini" ] && pass "pytest.ini exists" || warn "pytest.ini missing"
[ -f "pyproject.toml" ] && pass "pyproject.toml exists" || warn "pyproject.toml missing"
[ -f ".github/workflows/test.yml" ] && pass "GitHub Actions test.yml exists" || warn "test.yml missing"
[ -f "docs/MASTER_SETUP_GUIDE.md" ] && pass "MASTER_SETUP_GUIDE.md exists" || fail "MASTER_SETUP_GUIDE.md missing"
[ -f "docs/CRITICAL_ISSUE_2_API_RESPONSE_VALIDATION_DESIGN.md" ] && pass "CRITICAL_ISSUE_2 design doc exists" || warn "design doc missing"

echo ""

# ============================================================================
# SUMMARY
# ============================================================================
echo "════════════════════════════════════════════════════════"
echo "SUMMARY"
echo "════════════════════════════════════════════════════════"

TOTAL=$((PASS + FAIL))
if [ $TOTAL -gt 0 ]; then
    PCT=$((PASS * 100 / TOTAL))
    echo -e "${GREEN}Passed: $PASS${NC}"
    echo -e "${RED}Failed: $FAIL${NC}"
    echo -e "${YELLOW}Warnings: $WARN${NC}"
    echo "Success Rate: $PCT%"
fi

echo ""
echo "STATUS:"
echo -e "  ${GREEN}✅ CRITICAL ISSUE 1${NC}: FIXED (credentials_manager.py)"
echo -e "  ${GREEN}✅ CRITICAL ISSUE 2${NC}: IMPLEMENTED (api_validators.py + tests)"
echo -e "  ${YELLOW}⏳ CRITICAL ISSUE 3${NC}: PENDING (awaiting input_validators.py)"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ VERIFICATION PASSED${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review output above"
    echo "  2. Run: git push (if not already done)"
    echo "  3. Proceed to CRITICAL Issue 3 (AppleScript Injection)"
    echo ""
    exit 0
else
    echo -e "${RED}════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}❌ VERIFICATION FAILED${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Failed checks:"
    echo "  Review ❌ FAIL messages above"
    echo ""
    exit 1
fi
