# StorageRationalizer Dependency Management Plan

**Purpose:** Control package versions, prevent supply chain attacks, and maintain security compliance.

**Effective Date:** March 9, 2026
**Review Frequency:** Monthly
**Responsibility:** Project Lead + Security Team

---

## 1. Dependency Inventory

### Current Dependencies (as of March 9, 2026)

#### Core Runtime
| Package | Version | Purpose | License | CVE Status |
|---------|---------|---------|---------|------------|
| cryptography | [PINNED] | AES-256-GCM encryption | Apache 2.0 | ✅ Current |
| pytest | [PINNED] | Test framework | MIT | ✅ Current |
| pytest-cov | [PINNED] | Coverage reporting | MIT | ✅ Current |

#### Development & CI/CD
| Package | Version | Purpose | License | CVE Status |
|---------|---------|---------|---------|------------|
| black | [PINNED] | Code formatting | MIT | ✅ Current |
| flake8 | [PINNED] | Linting | MIT | ✅ Current |
| mypy | [PINNED] | Type checking | MIT | ✅ Current |
| detect-secrets | [PINNED] | Credential detection | Apache 2.0 | ✅ Current |
| pre-commit | [PINNED] | Git hooks | MIT | ✅ Current |

**Note:** All versions MUST be pinned to specific release tags. No `>=` or `~=` version specifiers.

### Storage Location
- **File:** `requirements.txt` (or `requirements-lock.txt` + `pyproject.toml`)
- **Format:** `package-name==exact.version.number`
- **Versioning:** Semantic versioning (MAJOR.MINOR.PATCH)

### Generating Locked Dependencies
```bash
# If using pip + requirements.txt:
pip freeze > requirements-lock.txt

# If using Poetry:
poetry lock

# If using Pipenv:
pipenv lock

# Commit locked file to repo
git add requirements-lock.txt
git commit -m "chore: update dependency lock"
```

---

## 2. Dependency Update Process

### Monthly Dependency Audit
**Schedule:** First Monday of every month
**Responsible:** Security Team

```bash
#!/bin/bash
# Monthly dependency check script

cd ~/Desktop/StorageRationalizer

echo "=== Step 1: Check for outdated packages ==="
pip list --outdated

echo "=== Step 2: Check for known CVEs ==="
# Using safety (install: pip install safety)
safety check --json > /tmp/safety_report.json

echo "=== Step 3: Review GitHub Dependabot alerts ==="
# Manual check: GitHub repo → Security → Dependabot alerts

echo "=== Step 4: Document findings ==="
# Update DEPENDENCY_UPDATE_LOG.txt with:
# - Date
# - Packages with available updates
# - CVEs found
# - Recommended actions
```

### Evaluating Updates

For each available update:

| Severity | Action | Timeline | Notes |
|----------|--------|----------|-------|
| CRITICAL CVE in dependency | Update immediately | 0-4 hours | P1 incident response |
| HIGH CVE in dependency | Schedule update | This sprint | P2 incident response |
| MEDIUM security update | Plan for next sprint | ≤30 days | Test thoroughly |
| Minor version update | Optional | Quarterly review | Only if benefits justify |
| Patch version update | Recommended | Monthly | Usually safe |

### Update Workflow

```bash
# 1. Create feature branch
git checkout -b chore/update-<package-name>

# 2. Update package(s)
pip install --upgrade <package-name>==<new-version>
pip freeze > requirements-lock.txt

# 3. Test thoroughly (REQUIRED)
pytest tests/ -v --cov
flake8 . --max-line-length=100
mypy . --ignore-missing-imports
black --check .

# 4. Run integration tests (if available)
python3 tests/integration_test.py

# 5. Verify no regressions
./verify_issues.sh

# 6. Commit & push
git add requirements-lock.txt
git commit -m "chore: update <package-name> to <version> - <reason>"
git push origin chore/update-<package-name>

# 7. Create PR and wait for GitHub Actions to pass
# 8. Code review (1 approval required)
# 9. Merge to main

# 10. Deploy & monitor
# Watch logs for errors related to updated package
```

### Rollback on Failure
```bash
# If update breaks production:
git revert <commit-hash>
git push origin main

# Investigate failure
# Document in DEPENDENCY_UPDATE_LOG.txt
# Update package maintainer issue if applicable
```

---

## 3. Supply Chain Security

### Risk Mitigation

#### A. Prevent Typosquatting
```bash
# Before installing any package, verify:
# 1. PyPI package page: https://pypi.org/project/<package>/
# 2. GitHub repository: https://github.com/<owner>/<repo>
# 3. Official documentation matches

# Example check:
pip search cryptography  # Check official name
pip show cryptography    # Verify installed version
pip index versions cryptography  # List all versions
```

#### B. Verify Package Signatures
```bash
# Some packages provide GPG signatures
# Verify if available:
gpg --verify <package>.tar.gz.asc <package>.tar.gz

# Download from official PyPI only:
pip install --index-url https://pypi.org/simple/ <package>
```

#### C. Audit Dependency Tree
```bash
# View full dependency tree
pip install pipdeptree
pipdeptree

# Check for circular dependencies
pipdeptree --warn fail

# Export for review
pipdeptree > /tmp/dependency_tree.txt
```

#### D. Monitor for Maintenance Status
```bash
# For each critical dependency:
# 1. Check last release date: https://pypi.org/project/<package>/#history
# 2. Check GitHub issues/PRs: https://github.com/<owner>/<repo>
# 3. Check maintainer commits in last 6 months
# 4. If unmaintained for 1+ year: consider alternative or fork

# Red flags:
# - No releases in 12+ months
# - Critical issues unanswered for 3+ months
# - Maintainer inactive on GitHub
# - Archived repository

# Document risk assessment in DEPENDENCY_UPDATE_LOG.txt
```

#### E. Lock Transitive Dependencies
```bash
# Always pin transitive deps (dependencies of dependencies)
# This is done automatically by:
pip freeze > requirements-lock.txt

# Verify no wildcards or ranges:
grep -E "[~>=<]" requirements-lock.txt  # Should return NOTHING

# All lines should be: package-name==X.Y.Z
```

---

## 4. Vulnerability Response

### GitHub Dependabot Integration
```yaml
# File: .github/dependabot.yml
# (If not already present, create it)

version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    reviewers:
      - "security-team"
    commit-message:
      prefix: "chore"
      include: "scope"
    pull-request-branch-name:
      separator: "/"
```

### Workflow on Dependabot Alert
```bash
# 1. GitHub notifies: Security → Dependabot alerts
# 2. Review alert: severity, affected versions, recommendation
# 3. If auto-update available: approve + merge PR
# 4. If manual: follow "Update Workflow" section above
# 5. Monitor for side effects after merge
# 6. Document in SECURITY_AUDIT_LOG.md
```

---

## 5. Quarterly Dependency Refresh

### Schedule: Every 3 months
**Next:** June 9, 2026

```bash
# Full dependency audit process
cd ~/Desktop/StorageRationalizer

# 1. Check all packages for updates
pip list --outdated

# 2. Review CVE databases
# - safety.io: safety check
# - snyk.io: snyk test
# - nvd.nist.gov: manual search

# 3. Evaluate major version updates (if available)
# - Check CHANGELOG for breaking changes
# - Test thoroughly (see Update Workflow)
# - Update documentation if APIs changed

# 4. Remove unused dependencies
pip show <package> | grep "Required by"
# If empty, consider removing

# 5. Update lock file
pip freeze > requirements-lock.txt

# 6. Create PR: "chore: quarterly dependency refresh"
# - Include changelog summary
# - Link to CVE fixes (if any)
# - Testing results

# 7. Document completion in DEPENDENCY_UPDATE_LOG.txt
```

---

## 6. Dependency Maintenance Log

**File:** `DEPENDENCY_UPDATE_LOG.txt`

```
=== StorageRationalizer Dependency Maintenance Log ===

[2026-03-09] INITIAL SETUP
- Pinned all dependencies
- Created requirements-lock.txt
- Enabled GitHub Dependabot
- Set up monthly audit schedule

[YYYY-MM-DD] UPDATE: <package-name>
- Old version: X.Y.Z
- New version: A.B.C
- Reason: [security update / feature / bug fix]
- CVE fixed: [CVE-XXXX-XXXXX if applicable]
- Tests: PASSED / FAILED
- Status: MERGED / REVERTED
- Notes: [any issues or concerns]

[YYYY-MM-DD] CVE ALERT: <CVE-XXXX-XXXXX>
- Affected package: <name>
- Affected versions: X.Y.Z - X.Y.W
- Severity: CRITICAL / HIGH / MEDIUM / LOW
- Status: PATCHED / MONITORED / ACCEPTED RISK
- Action taken: [what was done]
```

### Update Log Entry Template
```bash
# Add to DEPENDENCY_UPDATE_LOG.txt after each update:
[$(date +%Y-%m-%d)] UPDATE: <package-name>
- Old version: $(pip show <package> | grep Version)
- New version: <new-version>
- Reason: [brief description]
- CVE fixed: [if applicable]
- Tests: [PASSED/FAILED]
- Status: [MERGED/REVERTED]
- Notes: [optional]
```

---

## 7. Security Scanning in CI/CD

### GitHub Actions Integration

```yaml
# File: .github/workflows/security.yml
# (Ensure these sections are present)

name: Security Checks

on: [push, pull_request]

jobs:
  dependencies:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.9"

      - name: Install dependencies
        run: pip install -r requirements-lock.txt safety

      - name: Run safety check
        run: safety check --json

      - name: Run pip-audit
        run: pip install pip-audit && pip-audit
```

### Pre-commit Hook for Dependency Audit
```yaml
# File: .pre-commit-config.yaml
# (Add this hook if not present)

- repo: https://github.com/hadialqattan/pyt-upgrade
  rev: v21.3.4
  hooks:
    - id: py-upgrade
      args: [--py39-plus]

- repo: https://github.com/gitpod-io/workspace-full
  rev: master
  hooks:
    - id: safety-check
```

---

## 8. Disaster Recovery: Dependency Hell

### If you discover a broken dependency:

```bash
# 1. Identify the problem
pytest tests/ -v  # See which tests fail

# 2. Isolate the package
pip uninstall <suspect-package>
pytest tests/ -v  # Do tests pass now?

# 3. Check for alternatives
pip search <category>  # Find alternatives
google: "<package> alternative"

# 4. Evaluate replacement
# - Does it have similar API?
# - Is it actively maintained?
# - Does it have fewer dependencies?

# 5. If no alternative, downgrade
git log --oneline -20 | grep <package>
git show <commit> requirements-lock.txt  # Find old version
pip install <package>==<old-version>
pytest tests/ -v  # Verify

# 6. File issue with maintainer
# - GitHub issue on package repo
# - PyPI report form
# - Email security contacts (setup.py)

# 7. Document incident
# - Add to DEPENDENCY_UPDATE_LOG.txt
# - Add to INCIDENT_REPORTS/
```

---

## 9. Third-Party Audit & Compliance

### For external security audits:

```bash
# Generate dependency report
pip freeze > /tmp/dependency_report.txt
pipdeptree > /tmp/dependency_tree.txt
safety check --json > /tmp/safety_report.json

# Provide to auditor:
# - requirements-lock.txt (pinned versions)
# - DEPENDENCY_UPDATE_LOG.txt (maintenance history)
# - safety_report.json (CVE status)
# - dependency_tree.txt (transitive deps)

# Auditor checklist:
# [ ] All versions pinned? (no ranges)
# [ ] No known CVEs? (safety check)
# [ ] Dependencies actively maintained?
# [ ] License compliance? (no GPL unless approved)
# [ ] Supply chain security? (verified sources)
```

---

## 10. Policy & Schedule

### Monthly Tasks
- [ ] Run `safety check` (first Monday)
- [ ] Review Dependabot alerts
- [ ] Update DEPENDENCY_UPDATE_LOG.txt
- [ ] Check for critical CVEs

### Quarterly Tasks (Every 3 months)
- [ ] Full dependency refresh
- [ ] Audit for unused packages
- [ ] Review maintenance status of critical deps
- [ ] Update lock file
- [ ] Create refresh PR

### Annually (March 9)
- [ ] Comprehensive supply chain audit
- [ ] License compliance review
- [ ] Update this policy
- [ ] Train team on dependency management

---

## 11. Sign-Off

**Policy Effective:** March 9, 2026
**Last Reviewed:** March 9, 2026
**Next Review:** June 9, 2026 (quarterly)

**Responsible:** Project Lead + Security Team

---

## Quick Reference: Common Commands

```bash
# List outdated packages
pip list --outdated

# Check for CVEs
safety check

# View dependency tree
pipdeptree

# Pin all dependencies
pip freeze > requirements-lock.txt

# Update single package
pip install --upgrade <package>==<version>

# Verify all deps pinned
grep -E "[~>=<]" requirements-lock.txt  # Should be empty

# Run full test suite after update
pytest tests/ -v --cov && ./verify_issues.sh
```

---

## Appendix: Package Evaluation Template

**When considering a new dependency:**

```markdown
## Dependency Evaluation: [package-name]

### Purpose
[Why do we need this?]

### Alternatives Considered
- Option A: [pros/cons]
- Option B: [pros/cons]
- [package-name]: [pros/cons] ← CHOSEN

### Risk Assessment
- [ ] Actively maintained? (last commit: _____)
- [ ] Security: Any CVEs? (safety check result)
- [ ] License: Compatible? (Apache/MIT/BSD/etc)
- [ ] Size: Minimal dependencies? (pipdeptree output)
- [ ] Popularity: Used in production? (GitHub stars, downloads)
- [ ] Maintenance: Single maintainer risk? (GitHub contributors)

### Decision
- [x] APPROVED - add to requirements.txt
- [ ] REJECTED - use alternative
- [ ] HOLD - revisit in [timeframe]

### Responsible: _____ Date: _____
```
