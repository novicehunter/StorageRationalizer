#!/usr/bin/env bash
# =============================================================================
# StorageRationalizer — Audit Runner
# =============================================================================
#
# Orchestrates audit_runner.py and validates its outputs.
#
# Usage:
#   ./audit_runner.sh [full|quick|test-only|security-only|ci-cd-only|integrity-only]
#
# Examples:
#   ./audit_runner.sh full            # Full audit (~3-5 min)
#   ./audit_runner.sh quick           # Git + tests + risk (~2 min)
#   ./audit_runner.sh test-only       # Test coverage only
#   ./audit_runner.sh security-only   # Security audit only
#   ./audit_runner.sh ci-cd-only      # CI/CD deployment audit only
#   ./audit_runner.sh integrity-only  # Data integrity only
#
# Outputs:
#   docs/AUDIT_LOG_YYYY-MM-DD.md     — Comprehensive audit findings
#   docs/CLAUDE_SESSION_REFERENCE.md  — Summary for future Claude sessions
#   audit_cache.json                  — Raw JSON findings (for debugging)
#   logs/audit_YYYY-MM-DD.log         — Execution log
#
# Cron example (weekly Sunday 2 AM):
#   0 2 * * 0 cd /Users/$USER/Desktop/StorageRationalizer && ./audit_runner.sh full >> logs/cron_audit.log 2>&1
#
# =============================================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP="$(date +%Y-%m-%d)"
AUDIT_TYPE="${1:-full}"
OUTPUT_LOG="${SCRIPT_DIR}/docs/AUDIT_LOG_${TIMESTAMP}.md"
REFERENCE="${SCRIPT_DIR}/docs/CLAUDE_SESSION_REFERENCE.md"
LOG_DIR="${SCRIPT_DIR}/logs"
EXEC_LOG="${LOG_DIR}/audit_${TIMESTAMP}.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { echo -e "${BLUE}[INFO]${NC}  $*" | tee -a "${EXEC_LOG}"; }
success() { echo -e "${GREEN}[OK]${NC}    $*" | tee -a "${EXEC_LOG}"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*" | tee -a "${EXEC_LOG}"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" | tee -a "${EXEC_LOG}"; }
die()     { error "$*"; exit 1; }

# ── Validate audit type ───────────────────────────────────────────────────────
VALID_TYPES="full quick test-only security-only ci-cd-only integrity-only"
if ! echo "${VALID_TYPES}" | grep -qw "${AUDIT_TYPE}"; then
    echo "Usage: $0 [${VALID_TYPES// /|}]"
    echo ""
    echo "  full            Full audit (all 10 sections, ~3-5 min)"
    echo "  quick           Git status + test coverage + risk matrix (~2 min)"
    echo "  test-only       Test coverage only"
    echo "  security-only   Security + infrastructure checks"
    echo "  ci-cd-only      CI/CD + deployment readiness"
    echo "  integrity-only  Data integrity + git discrepancy check"
    exit 1
fi

# ── Pre-flight checks ─────────────────────────────────────────────────────────
mkdir -p "${LOG_DIR}" "${SCRIPT_DIR}/docs"

info "=================================================="
info "StorageRationalizer Audit — ${TIMESTAMP}"
info "Type: ${AUDIT_TYPE}"
info "Log: ${EXEC_LOG}"
info "=================================================="

# Check Python 3
if ! command -v python3 &>/dev/null; then
    die "python3 not found. Install Python 3.9+ to run audits."
fi
PYTHON_VERSION="$(python3 --version 2>&1)"
info "Python: ${PYTHON_VERSION}"

# Check audit_runner.py exists
if [[ ! -f "${SCRIPT_DIR}/audit_runner.py" ]]; then
    die "audit_runner.py not found in ${SCRIPT_DIR}"
fi

# Check we're in git repo
if ! git -C "${SCRIPT_DIR}" rev-parse --git-dir &>/dev/null; then
    die "Not a git repository: ${SCRIPT_DIR}"
fi

# Check required modules (minimal set for audit)
MISSING_DEPS=()
for module in ast sqlite3 re subprocess pathlib; do
    if ! python3 -c "import ${module}" &>/dev/null 2>&1; then
        MISSING_DEPS+=("${module}")
    fi
done
if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
    die "Missing Python modules: ${MISSING_DEPS[*]}"
fi

# Warn if pytest not available (some audit sections need it)
if ! python3 -m pytest --version &>/dev/null 2>&1; then
    warn "pytest not found — test coverage section will be limited"
fi

# Change to project root
cd "${SCRIPT_DIR}"

# ── Estimated time ────────────────────────────────────────────────────────────
case "${AUDIT_TYPE}" in
    full)           info "Estimated time: ~3-5 min (runs full pytest suite)" ;;
    quick)          info "Estimated time: ~2-3 min" ;;
    test-only)      info "Estimated time: ~2-3 min (runs pytest)" ;;
    security-only)  info "Estimated time: ~1 min" ;;
    ci-cd-only)     info "Estimated time: <1 min" ;;
    integrity-only) info "Estimated time: <1 min" ;;
esac

# ── Run audit_runner.py ───────────────────────────────────────────────────────
info "Starting audit engine …"
START_TIME=$(date +%s)

if python3 "${SCRIPT_DIR}/audit_runner.py" \
    --type "${AUDIT_TYPE}" \
    --output "${OUTPUT_LOG}" \
    --reference "${REFERENCE}" \
    --timestamp "${TIMESTAMP}" \
    --json-cache "${SCRIPT_DIR}/audit_cache.json" \
    2>&1 | tee -a "${EXEC_LOG}"; then
    AUDIT_RC=0
else
    AUDIT_RC=$?
fi

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))

# ── Validate outputs ──────────────────────────────────────────────────────────
info "Validating outputs …"
VALIDATION_PASSED=true

# Check audit log generated
if [[ -f "${OUTPUT_LOG}" ]]; then
    LOG_LINES="$(wc -l < "${OUTPUT_LOG}")"
    LOG_SIZE="$(du -sh "${OUTPUT_LOG}" | cut -f1)"
    success "Audit log: ${OUTPUT_LOG} (${LOG_LINES} lines, ${LOG_SIZE})"
else
    error "Audit log NOT generated: ${OUTPUT_LOG}"
    VALIDATION_PASSED=false
fi

# Check session reference generated
if [[ -f "${REFERENCE}" ]]; then
    REF_LINES="$(wc -l < "${REFERENCE}")"
    success "Session reference: ${REFERENCE} (${REF_LINES} lines)"
else
    error "Session reference NOT generated: ${REFERENCE}"
    VALIDATION_PASSED=false
fi

# Check JSON cache generated
if [[ -f "${SCRIPT_DIR}/audit_cache.json" ]]; then
    CACHE_SIZE="$(du -sh "${SCRIPT_DIR}/audit_cache.json" | cut -f1)"
    success "JSON cache: audit_cache.json (${CACHE_SIZE})"
else
    warn "JSON cache not generated"
fi

# Check audit log has expected sections
if [[ -f "${OUTPUT_LOG}" ]]; then
    MISSING_SECTIONS=()
    for section in "Phase 1" "Phase 2" "Phase 3" "Data Storage" "Git vs Local" \
                   "Test Coverage" "Infrastructure" "Security" "CI/CD" "Risk Matrix"; do
        if ! grep -q "${section}" "${OUTPUT_LOG}" 2>/dev/null; then
            MISSING_SECTIONS+=("${section}")
        fi
    done
    if [[ ${#MISSING_SECTIONS[@]} -gt 0 ]]; then
        warn "Missing sections in audit log: ${MISSING_SECTIONS[*]}"
    else
        success "All 10 audit sections present in audit log"
    fi
fi

# ── Extract key metrics from audit log ───────────────────────────────────────
if [[ -f "${OUTPUT_LOG}" ]]; then
    info "Key findings:"
    # Test results
    if grep -q "Passed:" "${OUTPUT_LOG}" 2>/dev/null; then
        PASSED_LINE="$(grep "Passed:" "${OUTPUT_LOG}" | head -1)"
        info "  Tests: ${PASSED_LINE}"
    fi
    # High risks
    HIGH_COUNT="$(grep -c "HIGH" "${OUTPUT_LOG}" 2>/dev/null || echo 0)"
    if [[ "${HIGH_COUNT}" -gt 0 ]]; then
        warn "  HIGH risk items: ${HIGH_COUNT} — review Risk Matrix section"
    fi
    # Overall coverage
    if grep -q "Overall coverage:" "${OUTPUT_LOG}" 2>/dev/null; then
        COV_LINE="$(grep "Overall coverage:" "${OUTPUT_LOG}" | head -1)"
        info "  ${COV_LINE}"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=================================================="
if [[ "${VALIDATION_PASSED}" == true ]] && [[ "${AUDIT_RC}" -eq 0 ]]; then
    success "AUDIT COMPLETE — ${ELAPSED}s"
    echo ""
    echo "  Audit log:       ${OUTPUT_LOG}"
    echo "  Session ref:     ${REFERENCE}"
    echo "  Execution log:   ${EXEC_LOG}"
    echo ""
    echo "Next steps:"
    echo "  1. Review: cat ${OUTPUT_LOG} | grep -A3 'Must-fix'"
    echo "  2. Review: cat ${REFERENCE}"
    echo "  3. Commit when satisfied: git add docs/ && git commit -m 'docs: audit ${TIMESTAMP}'"
else
    warn "AUDIT COMPLETED WITH WARNINGS (${ELAPSED}s)"
    echo ""
    echo "  Audit log:    ${OUTPUT_LOG:-NOT GENERATED}"
    echo "  Session ref:  ${REFERENCE:-NOT GENERATED}"
    echo "  Exit code:    ${AUDIT_RC}"
    echo ""
    echo "  Review execution log for details: cat ${EXEC_LOG}"
fi
echo "=================================================="

# Exit with audit_runner.py's exit code (0 even if findings exist — findings aren't errors)
exit "${AUDIT_RC}"
