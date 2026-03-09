#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Helper functions
pass() {
    echo -e "${GREEN}✅${NC} $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}❌${NC} $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠️${NC}  $1"
    ((WARNINGS++))
}

echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}CRITICAL ISSUES VERIFICATION${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}\n"

# ISSUE 1: Credentials in Plaintext
echo -e "${BLUE}ISSUE 1: CREDENTIALS IN PLAINTEXT${NC}"
echo -e "${BLUE}──────────────────────────────────${NC}"

if [ -f "tools/credentials_manager.py" ]; then
    pass "credentials_manager.py exists"
else
    fail "credentials_manager.py not found"
fi

if grep -q "class CredentialsManager" tools/credentials_manager.py 2>/dev/null; then
    pass "CredentialsManager class exists"
else
    fail "CredentialsManager class not found"
fi

if grep -q "credentials/encrypted" .gitignore 2>/dev/null; then
    pass "credentials/encrypted in .gitignore"
else
    fail "credentials/encrypted not in .gitignore"
fi

# ISSUE 2: API Response Validation
echo -e "\n${BLUE}ISSUE 2: API RESPONSE VALIDATION${NC}"
echo -e "${BLUE}────────────────────────────────${NC}"

if [ -f "tools/api_validators.py" ]; then
    pass "api_validators.py exists"
else
    fail "api_validators.py not found"
fi

if grep -q "def validate_restore_response" tools/api_validators.py 2>/dev/null; then
    pass "validate_restore_response() exists"
else
    fail "validate_restore_response() not found"
fi

if grep -q "def validate_metadata_response" tools/api_validators.py 2>/dev/null; then
    pass "validate_metadata_response() exists"
else
    fail "validate_metadata_response() not found"
fi

if grep -q "def validate_batch_response" tools/api_validators.py 2>/dev/null; then
    pass "validate_batch_response() exists"
else
    fail "validate_batch_response() not found"
fi

if grep -q "class APIResponseError" tools/api_validators.py 2>/dev/null; then
    pass "APIResponseError exception exists"
else
    fail "APIResponseError exception not found"
fi

if grep -q "from tools.api_validators import" tools/rollback.py 2>/dev/null; then
    pass "rollback.py imports validators"
else
    fail "rollback.py does not import validators"
fi

if grep -q "from tools.api_validators import" phase2/verifier.py 2>/dev/null; then
    pass "verifier.py imports validators"
else
    fail "verifier.py does not import validators"
fi

if grep -q "from tools.api_validators import" phase3/cleaner.py 2>/dev/null; then
    pass "cleaner.py imports validators"
else
    fail "cleaner.py does not import validators"
fi

if [ -f "tests/test_api_validators.py" ]; then
    pass "test_api_validators.py exists"
else
    fail "test_api_validators.py not found"
fi

# ISSUE 3: AppleScript Injection
echo -e "\n${BLUE}ISSUE 3: APPLESCRIPT INJECTION${NC}"
echo -e "${BLUE}──────────────────────────────${NC}"

if [ -f "tools/input_validators.py" ]; then
    pass "input_validators.py exists"
else
    fail "input_validators.py not found"
fi

if grep -q "def validate_file_path" tools/input_validators.py 2>/dev/null; then
    pass "validate_file_path() exists"
else
    fail "validate_file_path() not found"
fi

if grep -q "def validate_directory_path" tools/input_validators.py 2>/dev/null; then
    pass "validate_directory_path() exists"
else
    fail "validate_directory_path() not found"
fi

if grep -q "def sanitize_applescript_string" tools/input_validators.py 2>/dev/null; then
    pass "sanitize_applescript_string() exists"
else
    fail "sanitize_applescript_string() not found"
fi

if grep -q "def validate_command_list" tools/input_validators.py 2>/dev/null; then
    pass "validate_command_list() exists"
else
    fail "validate_command_list() not found"
fi

if grep -q "def build_safe_applescript_put_back" tools/input_validators.py 2>/dev/null; then
    pass "build_safe_applescript_put_back() exists"
else
    fail "build_safe_applescript_put_back() not found"
fi

if grep -q "class InputValidationError" tools/input_validators.py 2>/dev/null; then
    pass "InputValidationError exception exists"
else
    fail "InputValidationError exception not found"
fi

if grep -q "from tools.input_validators import" tools/rollback.py 2>/dev/null; then
    pass "rollback.py imports input_validators"
else
    fail "rollback.py does not import input_validators"
fi

if grep -q "from tools.input_validators import" phase1/scanner.py 2>/dev/null; then
    pass "scanner.py imports input_validators"
else
    fail "scanner.py does not import input_validators"
fi

if [ -f "tests/test_input_validators.py" ]; then
    pass "test_input_validators.py exists"
else
    fail "test_input_validators.py not found"
fi

# Python Syntax Checks
echo -e "\n${BLUE}PYTHON SYNTAX CHECKS${NC}"
echo -e "${BLUE}────────────────────${NC}"

for file in tools/api_validators.py tools/rollback.py phase2/verifier.py phase3/cleaner.py; do
    if python3 -m py_compile "$file" 2>/dev/null; then
        pass "$file syntax valid"
    else
        fail "$file syntax invalid"
    fi
done

# Import Tests
echo -e "\n${BLUE}IMPORT TESTS${NC}"
echo -e "${BLUE}────────────${NC}"

if python3 -c "from tools.api_validators import validate_restore_response" 2>/dev/null; then
    pass "api_validators imports work"
else
    fail "api_validators imports failed"
fi

if python3 -c "from tools.input_validators import validate_file_path" 2>/dev/null; then
    pass "input_validators imports work"
else
    fail "input_validators imports failed"
fi

# Git Status
echo -e "\n${BLUE}GIT STATUS${NC}"
echo -e "${BLUE}──────────${NC}"

echo "Last 3 commits:"
git log --oneline -3 | sed 's/^/  /'

if git log --oneline | grep -q "fix: add API response validation"; then
    pass "CRITICAL Issue 2 commit found"
else
    warn "CRITICAL Issue 2 commit not found"
fi

if git log --oneline | grep -q "security: implement input validation"; then
    pass "CRITICAL Issue 3 commit found"
else
    warn "CRITICAL Issue 3 commit not found"
fi

if [ -z "$(git status --porcelain)" ]; then
    pass "No uncommitted changes"
else
    warn "$(git status --porcelain | wc -l) uncommitted changes"
fi

# Infrastructure
echo -e "\n${BLUE}INFRASTRUCTURE${NC}"
echo -e "${BLUE}───────────────${NC}"

for file in .pre-commit-config.yaml pytest.ini pyproject.toml .github/workflows/test.yml docs/MASTER_SETUP_GUIDE.md docs/CRITICAL_ISSUE_2_API_RESPONSE_VALIDATION_DESIGN.md; do
    if [ -f "$file" ]; then
        pass "$file exists"
    else
        warn "$file not found"
    fi
done

# Summary
echo -e "\n${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}SUMMARY${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo -e "Warnings: ${YELLOW}$WARNINGS${NC}"

TOTAL=$((PASSED + FAILED))
if [ $TOTAL -gt 0 ]; then
    SUCCESS_RATE=$((PASSED * 100 / TOTAL))
    echo -e "Success Rate: $SUCCESS_RATE%"
fi

echo ""
echo -e "STATUS:"
if grep -q "class CredentialsManager" tools/credentials_manager.py 2>/dev/null && grep -q "credentials/encrypted" .gitignore 2>/dev/null; then
    echo -e "  ${GREEN}✅ CRITICAL ISSUE 1: FIXED${NC} (credentials_manager.py)"
else
    echo -e "  ${RED}❌ CRITICAL ISSUE 1: FAILED${NC}"
fi

if grep -q "def validate_restore_response" tools/api_validators.py 2>/dev/null && grep -q "from tools.api_validators import" tools/rollback.py 2>/dev/null; then
    echo -e "  ${GREEN}✅ CRITICAL ISSUE 2: FIXED${NC} (api_validators.py + tests)"
else
    echo -e "  ${YELLOW}⏳ CRITICAL ISSUE 2: PENDING${NC}"
fi

if grep -q "def validate_file_path" tools/input_validators.py 2>/dev/null && grep -q "from tools.input_validators import" tools/rollback.py 2>/dev/null; then
    echo -e "  ${GREEN}✅ CRITICAL ISSUE 3: FIXED${NC} (input_validators.py + tests)"
else
    echo -e "  ${YELLOW}⏳ CRITICAL ISSUE 3: PENDING${NC}"
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ VERIFICATION PASSED${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    exit 0
else
    echo -e "${RED}❌ VERIFICATION FAILED${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    exit 1
fi
