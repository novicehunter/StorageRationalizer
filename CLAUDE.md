# StorageRationalizer Development Context (CLAUDE.md)

**Purpose:** Project context for future development sessions. References security state, governance, and workflow rules.

**Last Updated:** March 9, 2026
**Status:** Phase 3 Complete ✅

---

## 🎯 Project Overview

**StorageRationalizer** is an intelligent cloud storage deduplication and recovery tool for macOS that:
- Discovers duplicate files in OneDrive and Google Drive
- Restores files safely with full data integrity verification
- Uses AES-256-GCM encryption for credentials
- Validates all API responses to prevent silent failures
- Sanitizes all inputs to prevent command injection attacks

**Repository:** https://github.com/novicehunter/StorageRationalizer
**Status:** Production Ready (Phase 3 Complete)

---

## ✅ Current Status (as of March 9, 2026)

### Phase 1: Security Fixes ✅ COMPLETE
All 3 CRITICAL vulnerabilities fixed and tested:
1. **Credentials in plaintext** → Fixed with AES-256-GCM encryption
2. **Silent API failures** → Fixed with response validation
3. **AppleScript injection** → Fixed with input sanitization

**Tests:** 49/49 passing | **Coverage:** ≥90%

**Key Commits:**
- `df1d92e` — Add governance docs (Phase 3)
- `c9462e9` — AppleScript injection prevention
- `1b004cc` — API response validation
- `5e1ff14` — CI/CD setup

### Phase 2: Code Quality ✅ COMPLETE
- Pre-commit hooks: black, flake8, mypy, detect-secrets
- GitHub Actions: Automated testing + security scanning
- All code: 0 linting errors, 0 type errors, all black-formatted

### Phase 3: Governance ✅ COMPLETE
Six production-ready operational documents added:
1. `SECURITY_AUDIT_LOG.md` — Compliance trail
2. `INCIDENT_RESPONSE_RUNBOOK.md` — Incident procedures (P1-P4)
3. `ACCESS_CONTROL_POLICY.md` — Role-based access + code review
4. `DEPENDENCY_MANAGEMENT_PLAN.md` — Supply chain security + CVE response
5. `MONITORING_AND_ALERTING.md` — Log aggregation + alert rules
6. `EXTENDED_TESTING_PLAN.md` — Integration, performance, penetration testing roadmap

**Commit:** `df1d92e` (March 9, 2026)

---

## 📁 Repository Structure

```
StorageRationalizer/
├── tools/                              # Core security modules
│   ├── credentials_manager.py          # AES-256-GCM (Issue #1 fix)
│   ├── api_validators.py               # Response validation (Issue #2 fix)
│   ├── input_validators.py             # Input sanitization (Issue #3 fix)
│   └── rollback.py                     # Safe file restoration
├── phase1/scanner.py                   # File discovery
├── phase2/verifier.py                  # Metadata verification
├── phase3/cleaner.py                   # Batch operations
├── tests/                              # 49 unit tests
│   ├── test_api_validators.py          # 13 tests, 74% coverage
│   └── test_input_validators.py        # 36 tests, 95% coverage
├── docs/                               # 9 documentation files
│   ├── SECURITY_REMEDIATION_COMPLETION_REPORT.md
│   ├── MASTER_SETUP_GUIDE.md
│   ├── CRITICAL_ISSUE_2_API_RESPONSE_VALIDATION_DESIGN.md
│   ├── SECURITY_AUDIT_LOG.md           # NEW - Phase 3
│   ├── INCIDENT_RESPONSE_RUNBOOK.md    # NEW - Phase 3
│   ├── ACCESS_CONTROL_POLICY.md        # NEW - Phase 3
│   ├── DEPENDENCY_MANAGEMENT_PLAN.md   # NEW - Phase 3
│   ├── MONITORING_AND_ALERTING.md      # NEW - Phase 3
│   └── EXTENDED_TESTING_PLAN.md        # NEW - Phase 3
├── .github/workflows/                  # GitHub Actions
│   ├── test.yml                        # Run tests on push/PR
│   └── security.yml                    # Security scanning
├── .pre-commit-config.yaml             # Git hooks
├── pytest.ini                          # Test config
├── requirements.txt                    # Dependencies (pinned versions)
├── verify_issues.sh                    # Security verification script
└── README.md                           # User-facing documentation
```

---

## 🔐 Security Architecture

### Issue #1: Credentials in Plaintext → FIXED ✅
**File:** `tools/credentials_manager.py`
**Solution:** AES-256-GCM encryption
**Key Methods:**
- `save_credential(key, value)` — Encrypt and store
- `get_credential(key)` — Decrypt at runtime
- `delete_credential(key)` — Securely remove
**Storage:** `credentials/encrypted/` (git-ignored)
**Tests:** Integrated in `test_input_validators.py`

### Issue #2: Silent API Failures → FIXED ✅
**File:** `tools/api_validators.py`
**Solution:** Strict response schema validation
**Key Functions:**
- `validate_restore_response(response)` — OneDrive restore validation
- `validate_metadata_response(response)` — Google Drive metadata validation
- `validate_batch_response(response)` — Batch operation validation
**Coverage:** 13 tests, 74% coverage
**Integration:** `phase2/verifier.py`, `phase3/cleaner.py`, `tools/rollback.py`

### Issue #3: AppleScript Injection → FIXED ✅
**File:** `tools/input_validators.py`
**Solution:** Input validation + subprocess hardening
**Key Functions:**
- `validate_file_path(path)` — Path normalization + restricted dir blocking
- `validate_directory_path(path)` — Directory validation
- `sanitize_applescript_string(s)` — AppleScript escaping
- `build_safe_applescript_put_back(path)` — Safe AppleScript generation
**Threats Prevented:** Shell injection, AppleScript injection, path traversal, TOCTOU races, symlink attacks
**Coverage:** 36 tests, 95% coverage
**Integration:** `tools/rollback.py` (uses `subprocess.run` with `shell=False`)

---

## 🧪 Testing Strategy

### Current: Unit Tests (49 tests) ✅
```bash
pytest tests/ -v --cov
```
- `test_api_validators.py` — 13 tests, 74% coverage
- `test_input_validators.py` — 36 tests, 95% coverage
- All pass, 0 failures
- Pre-commit hooks: All pass

### Upcoming: Extended Testing (Q2-Q3 2026)
**Phase 2:** Integration tests (50+ new tests)
- Credential manager integration
- API validator integration (mock OneDrive/Google Drive)
- File operations integration
- End-to-end scenarios

**Phase 3:** Performance tests (20+ tests)
- Throughput: credential access, API validation
- Concurrency: thread safety
- Load: 100+ files, 10,000+ credentials

**Phase 4:** Security tests (60+ tests)
- Penetration testing: 50+ injection payloads
- Vulnerability scanning: dependency CVEs
- Manual audit: file system security, TOCTOU races

See: `docs/EXTENDED_TESTING_PLAN.md`

---

## 📋 Governance & Operations

### Code Review Rules
**For security modules (`tools/credentials_manager.py`, `tools/api_validators.py`, `tools/input_validators.py`):**
- ✅ 1 approving review required (Tier 3+ only)
- ✅ All tests pass
- ✅ All pre-commit hooks pass
- ✅ No new security warnings

**For other changes:**
- ✅ All tests pass
- ✅ Pre-commit hooks pass

See: `docs/ACCESS_CONTROL_POLICY.md`

### Commit Discipline
**All commits MUST:**
1. Have a descriptive message: `type: description (issue reference)`
2. Pass pre-commit hooks: `black`, `flake8`, `mypy`, `detect-secrets`
3. Be signed (GPG): `git commit -S -m "message"`
4. Reference related issues: `fixes #123`

**Commit Types:**
- `security:` — Security fixes or hardening
- `fix:` — Bug fixes
- `feature:` — New features
- `chore:` — Maintenance, deps, cleanup
- `docs:` — Documentation
- `ci:` — CI/CD changes
- `refactor:` — Code refactoring

### Dependency Management
**All versions MUST be pinned** (no `>=`, `~=`, etc.):
```
cryptography==41.0.7
pytest==7.4.3
black==23.12.1
```

**Monthly audit:**
```bash
safety check
pip list --outdated
```

**CVE response:**
- CRITICAL: <4 hours
- HIGH: <24 hours
- MEDIUM: <30 days

See: `docs/DEPENDENCY_MANAGEMENT_PLAN.md`

### Incident Response
**If security issue discovered:**
1. Classify: P1 (critical), P2 (high), P3 (medium), P4 (low)
2. Respond: <1h (P1), <4h (P2), <24h (P3)
3. Fix: Follow remediation template
4. Test: Full test suite + security tests
5. Document: Update audit log

See: `docs/INCIDENT_RESPONSE_RUNBOOK.md`

### Monitoring & Alerting
**What's monitored:**
- Credential decryption failures
- API validation failures
- Injection attempts
- Dependency CVEs
- Test failures

**Alert channels:**
- P1: Immediate (Slack + PagerDuty)
- P2: Urgent (Slack, <1 hour)
- P3: Daily summary (email)

See: `docs/MONITORING_AND_ALERTING.md`

---

## 🚀 Development Workflow

### Before Starting Work
1. Check current status: `git status`, `git log -5`
2. Pull latest: `git pull origin main`
3. Review security state: `./verify_issues.sh`
4. Run tests: `pytest tests/ -v`

### Adding a Feature
```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes
# ... write code ...

# Test
pytest tests/ -v --cov

# Pre-commit
pre-commit run --all-files

# Commit
git add .
git commit -S -m "feature: add my feature - fixes #123"

# Push
git push origin feature/my-feature

# Create PR on GitHub
# - Link to issue
# - Request 1 review (if security module)
# - Wait for GitHub Actions to pass
# - Merge via PR
```

### Security Module Changes
```bash
# Only for: tools/credentials_manager.py, tools/api_validators.py, tools/input_validators.py

git checkout -b security/fix-<issue-name>

# Make changes + test
pytest tests/test_api_validators.py tests/test_input_validators.py -v --cov

# Verify with script
./verify_issues.sh

# Pre-commit hooks
pre-commit run --all-files

# Commit (MUST be signed)
git commit -S -m "security: fix <issue> - fixes CRITICAL Issue #N"

# Code review required (1 approval minimum)
# After approval: merge via GitHub PR
```

### Running Tests Locally
```bash
# All tests
pytest tests/ -v --cov

# Specific test file
pytest tests/test_api_validators.py -v

# Specific test
pytest tests/test_api_validators.py::TestValidators::test_valid_response -v

# With coverage report
pytest tests/ --cov=tools --cov-report=html
open htmlcov/index.html
```

### Code Quality Checks
```bash
# Format (auto-fixes)
black tools/ phase*/

# Lint
flake8 tools/ phase*/ --max-line-length=100

# Type check
mypy tools/ phase*/ --ignore-missing-imports

# All at once
pre-commit run --all-files
```

---

## 📚 Documentation Map

**For End Users:**
- `README.md` — Quick start, overview, security status
- `docs/SECURITY_REMEDIATION_COMPLETION_REPORT.md` — What was fixed

**For Operations/Security:**
- `docs/SECURITY_AUDIT_LOG.md` — Compliance trail
- `docs/INCIDENT_RESPONSE_RUNBOOK.md` — How to respond to incidents
- `docs/MONITORING_AND_ALERTING.md` — What's monitored, how to alert
- `docs/ACCESS_CONTROL_POLICY.md` — Who can do what

**For Developers:**
- `docs/MASTER_SETUP_GUIDE.md` — CI/CD infrastructure
- `docs/CRITICAL_ISSUE_2_API_RESPONSE_VALIDATION_DESIGN.md` — API validation deep dive
- `docs/DEPENDENCY_MANAGEMENT_PLAN.md` — Dependency updates, CVE response
- `docs/EXTENDED_TESTING_PLAN.md` — Integration, performance, penetration testing roadmap
- `CLAUDE.md` — This file (project context)

---

## 🔍 Verification Commands

**Quick health check:**
```bash
./verify_issues.sh
```

**Full test suite:**
```bash
pytest tests/ -v --cov
```

**Pre-commit hooks:**
```bash
pre-commit run --all-files
```

**Git history (recent):**
```bash
git log --oneline -20
```

**Current branch status:**
```bash
git status
git branch -a
```

---

## ⚠️ Common Issues & Solutions

### Pre-commit fails with `detect-secrets`
```bash
# Mark false positive with:
# pragma: allowlist secret

# Or temporarily skip:
git commit --no-verify
```

### Tests fail after dependency update
```bash
# Reinstall dependencies
pip install -r requirements.txt
pytest tests/ -v
```

### AppleScript validation rejects valid path
```bash
# Check if path:
# - Contains symlinks (rejected)
# - Is in restricted dirs (/System, /Library, /Applications, /Volumes)
# - Has invalid characters
# Debug: python3 -c "from tools.input_validators import validate_file_path; print(validate_file_path('/your/path'))"
```

### Credential access fails
```bash
# Verify encryption key exists
ls credentials/encrypted/

# Check permissions
chmod 700 credentials/

# Test decryption
python3 -c "from tools.credentials_manager import CredentialManager; cm = CredentialManager(); print(cm.get_credential('test'))"
```

---

## 🎯 Next Phase: Extended Testing (Q2-Q3 2026)

**Phase 2 (Q2):** Integration testing
- Mock OneDrive/Google Drive API calls
- Test credential manager with real crypto
- Test file operations with symlinks
- End-to-end restore scenarios

**Phase 3 (Q2):** Performance testing
- Throughput: 1000 credential accesses/sec
- Concurrency: 10 threads accessing same credential store
- Load: 100+ files, 10,000+ credentials in store

**Phase 4 (Q3):** Security testing
- Penetration: 50+ injection payloads
- Vulnerability: CVE scanning (Dependabot)
- Manual audit: file system race conditions, TOCTOU vulnerabilities

**Target:** 150+ tests, ≥95% coverage by August 2026

See: `docs/EXTENDED_TESTING_PLAN.md`

---

## 📞 Quick Links

| Need | Link |
|------|------|
| Security issue | [`docs/INCIDENT_RESPONSE_RUNBOOK.md`](docs/INCIDENT_RESPONSE_RUNBOOK.md) |
| Code review requirements | [`docs/ACCESS_CONTROL_POLICY.md`](docs/ACCESS_CONTROL_POLICY.md) |
| Dependency update | [`docs/DEPENDENCY_MANAGEMENT_PLAN.md`](docs/DEPENDENCY_MANAGEMENT_PLAN.md) |
| Monitoring/alerts | [`docs/MONITORING_AND_ALERTING.md`](docs/MONITORING_AND_ALERTING.md) |
| Testing plan | [`docs/EXTENDED_TESTING_PLAN.md`](docs/EXTENDED_TESTING_PLAN.md) |
| Audit trail | [`docs/SECURITY_AUDIT_LOG.md`](docs/SECURITY_AUDIT_LOG.md) |

---

## 📝 Session Notes

**Last Session:** March 9, 2026
- ✅ Phase 3 governance docs created (6 files)
- ✅ All docs committed to main
- ✅ README updated with full phase coverage
- ✅ CLAUDE.md updated with current status
- ✅ Cache artifacts cleaned (.pytest_cache, __pycache__)

**Current Status:** Phase 3/3 Complete — Production Ready ✅

**Next Session:** Start Phase 4 (Extended Testing)
- Review `docs/EXTENDED_TESTING_PLAN.md`
- Begin integration test development
- Set up performance test harness

---

**For future sessions, use this file as context.** All critical information is documented in `docs/`. No further action needed unless actively developing Phase 4.
