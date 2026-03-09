# StorageRationalizer Incident Response Runbook

**Purpose:** Step-by-step procedures to respond to security incidents, vulnerabilities, or breaches.

**Last Updated:** March 9, 2026
**Severity Levels:** CRITICAL (P1), HIGH (P2), MEDIUM (P3), LOW (P4)
**On-Call:** Security team (escalate via GitHub Issues)

---

## 1. Incident Classification

### P1 - CRITICAL (Response: Immediate)
- Active exploitation in production
- Credentials exposed/leaked
- Unauthorized code execution
- Data breach confirmed

**Response Time:** < 1 hour

### P2 - HIGH (Response: Urgent)
- Unpatched vulnerability affecting security modules
- Failed security test in CI/CD
- Dependency with known CVE

**Response Time:** < 4 hours

### P3 - MEDIUM (Response: Planned)
- New vulnerability discovered, not yet exploited
- Test coverage gap in security code
- Missing pre-commit validation

**Response Time:** < 24 hours

### P4 - LOW (Response: Backlog)
- Minor code quality issue
- Documentation gap
- Process improvement suggestion

**Response Time:** Next sprint

---

## 2. P1 CRITICAL: Active Breach Response

### 2.1 Immediate Actions (0-15 min)
```bash
# 1. Stop the bleeding
pkill -f StorageRationalizer  # Stop any running processes
sudo iptables -I INPUT -j DROP  # (optional) Block network if needed

# 2. Preserve evidence
cd ~/Desktop/StorageRationalizer
git log --all --oneline > /tmp/incident_git_log.txt
git status > /tmp/incident_git_status.txt
ps aux | grep -i storage > /tmp/incident_processes.txt
netstat -tanu | grep ESTABLISHED > /tmp/incident_network.txt

# 3. Notify immediately
# - Post to #security Slack channel
# - Email security@company.com
# - Create GitHub Security Advisory (GitHub repo -> Security -> Advisories)

# 4. Isolate affected systems
# - Disable API keys/credentials
# - Revoke recent deployments
# - Block external API calls
```

### 2.2 Investigation (15-60 min)
```bash
# Check logs for breach indicators
cd ~/Desktop/StorageRationalizer
grep -r "ERROR\|FAIL\|UNAUTHORIZED" logs/ > /tmp/incident_errors.txt

# Review recent commits for malicious changes
git log --oneline -20
git diff HEAD~5..HEAD --stat

# Check for credential exposure
grep -r "password\|api_key\|secret\|token" --include="*.py" --include="*.json" .

# Verify file integrity
./verify_issues.sh

# Review API response logs
tail -100 logs/api_responses.log
```

### 2.3 Containment (60-120 min)
```bash
# 1. Revoke compromised credentials
python3 << 'EOF'
from tools.credentials_manager import CredentialManager
cm = CredentialManager()
# Get list of all stored credentials
# Rotate each one (in your credential system)
# Document rotation in SECURITY_AUDIT_LOG.md
EOF

# 2. Patch the vulnerability
# - Identify root cause
# - Write fix (see Section 4: Remediation Template)
# - Run tests: pytest tests/ -v --cov

# 3. Roll back if necessary
git revert <commit_hash>
git push origin main

# 4. Deploy patched version
git push origin main
# (GitHub Actions will run security tests automatically)
```

### 2.4 Post-Incident (2-24 hours)
```bash
# 1. Root cause analysis
# Document in: docs/INCIDENT_REPORTS/<date>_RCA.md

# 2. Update SECURITY_AUDIT_LOG.md
# Add entry to "Incident & Vulnerability Disclosure Log"

# 3. Update this runbook if procedures failed

# 4. Schedule incident review meeting
# Attendees: dev team, security, ops
# Duration: 1 hour
# Output: action items, timeline, communications

# 5. Publish postmortem (external if user-facing breach)
# Template: docs/POSTMORTEM_TEMPLATE.md
```

---

## 3. P2 HIGH: Unpatched Vulnerability

### 3.1 Assessment (0-30 min)
```bash
# 1. Verify impact
cd ~/Desktop/StorageRationalizer
./verify_issues.sh  # Do security checks still pass?

# 2. Check if vulnerability affects production
git log --oneline --grep="<vulnerability>" -5
git branch -a --contains <vulnerable_commit>

# 3. Evaluate risk
# - Is exploit available? (search CVE databases)
# - Is code path reachable in production?
# - Can it be exploited remotely or locally only?
```

### 3.2 Remediation (30 min - 4 hours)
```bash
# 1. Create feature branch
git checkout -b security/fix-<vulnerability-name>

# 2. Implement fix (see Section 4: Remediation Template)

# 3. Test thoroughly
pytest tests/ -v --cov
flake8 . --max-line-length=100
mypy . --ignore-missing-imports

# 4. Request code review (if team available)
# Otherwise: ensure pre-commit hooks pass

# 5. Merge & deploy
git add .
git commit -m "security: fix <vulnerability> - closes GitHub issue #<N>"
git push origin security/fix-<vulnerability-name>
git checkout main
git merge --no-ff security/fix-<vulnerability-name>
git push origin main
```

### 3.3 Verification (post-deploy)
```bash
# 1. Run verification suite
./verify_issues.sh

# 2. Monitor logs for errors
tail -f logs/*.log

# 3. Test with end-to-end scenario
python3 tests/integration_test.py  # (if exists)
```

---

## 4. Remediation Template (for any P1/P2 fix)

**File:** `docs/INCIDENT_REPORTS/<date>_FIX_<ISSUE>.md`

```markdown
# Security Fix Report: [Vulnerability Name]

**Date:** YYYY-MM-DD
**Severity:** CRITICAL / HIGH
**Status:** IN PROGRESS / RESOLVED

## Summary
[One sentence describing the vulnerability]

## Root Cause
[What allowed this to happen?]

## Impact
- [ ] Credentials exposed? [YES/NO]
- [ ] Code execution possible? [YES/NO]
- [ ] Data breach possible? [YES/NO]
- Affected versions: [list]
- Affected users/systems: [list]

## Fix Details
- **File(s) changed:** [list]
- **Lines of code:** [before/after]
- **Testing:** [test cases added]
- **Commit hash:** [commit]

## Verification
```bash
./verify_issues.sh
pytest tests/ -v --cov
```

## References
- GitHub Issue: [#N]
- CVE: [if applicable]
- External advisory: [URL]

## Sign-Off
- [ ] Code review passed
- [ ] Tests passing
- [ ] Deployed to main
- [ ] Audit log updated
```

---

## 5. P3 MEDIUM: Vulnerability Discovery

### Detection Methods
1. **Automated:** GitHub Dependabot, security scanning, SAST tools
2. **Manual:** Code review, penetration testing, security research
3. **External:** CVE disclosures, bug bounty reports, security advisories

### Response Workflow
```bash
# 1. Create GitHub issue
# Labels: [security], [severity: medium]
# Include: vulnerability description, impact, timeline

# 2. Plan remediation
# Assign to developer
# Set deadline: next sprint

# 3. Implement (see Section 4 template)

# 4. Verify (see P2 verification)

# 5. Document & close issue
```

---

## 6. Dependency Vulnerability (P2 or P3)

### When notified of CVE in dependency:
```bash
cd ~/Desktop/StorageRationalizer

# 1. Check if vulnerable version is installed
pip show <package_name>
grep <package_name> requirements.txt

# 2. Update to patched version
pip install --upgrade <package_name>

# 3. Re-run all tests
pytest tests/ -v --cov

# 4. Commit & push
git add requirements.txt
git commit -m "security: update <package> to <version> - fixes CVE-XXXX-XXXXX"
git push origin main

# 5. Update SECURITY_AUDIT_LOG.md
```

---

## 7. Monitoring & Alerting

### What to Monitor
```yaml
Credentials:
  - Failed decryption attempts (logs/credentials.log)
  - Missing encryption key

API Responses:
  - Silent failures (status without body)
  - Validation errors

File Operations:
  - AppleScript injection attempts
  - Symlink traversal attempts
  - Permission denied errors

Infrastructure:
  - Unauthorized API calls
  - Rate limit exceeded
  - Network timeouts
```

### Alert Thresholds
- **P1:** 5+ credential errors in 5 min → immediate alert
- **P2:** 10+ API validation errors in 1 hour → page on-call
- **P3:** 1+ symlink traversal attempt → daily summary

### Logging Template
```python
import logging
logger = logging.getLogger(__name__)

# Security event logging
logger.critical(f"SECURITY: Credential decryption failed for key={key_id}")
logger.warning(f"SECURITY: API response validation failed: {response_hash}")
logger.info(f"SECURITY: File operation blocked: {reason}")
```

---

## 8. Communication Plan

### Internal Escalation
```
Developer → On-Call Security → Security Manager → CISO
```

### External Notification (if user-facing breach)
```
1. Notify legal/compliance within 1 hour
2. Draft user notification within 4 hours
3. Publish advisory within 24 hours
4. Include: what happened, what we're doing, what users should do
```

### Status Updates
- **P1:** Every 15 min until contained, then hourly
- **P2:** Every 4 hours
- **P3:** Daily summary

---

## 9. Post-Incident Checklist

- [ ] Incident classified and documented
- [ ] Vulnerability fixed and tested
- [ ] Root cause identified
- [ ] Fix deployed to production
- [ ] Audit log updated (SECURITY_AUDIT_LOG.md)
- [ ] Incident report written (docs/INCIDENT_REPORTS/)
- [ ] Team debriefing scheduled
- [ ] Runbook updated (this file)
- [ ] Communication sent (internal + external if needed)
- [ ] Postmortem scheduled (P1 only)

---

## 10. Contact & Escalation

| Role | Contact | Available |
|------|---------|-----------|
| Security Team | security@company.com | Always (via GitHub) |
| On-Call | Slack #security | 24/7 |
| CISO | ciso@company.com | For P1 only |

**GitHub Security Advisory:** https://github.com/novicehunter/StorageRationalizer/security/advisories

---

## 11. Annual Review

- [ ] Review this runbook annually
- [ ] Test procedures in drill scenario
- [ ] Update contact information
- [ ] Verify tooling is still functional
- [ ] Train new team members

**Last Review:** March 9, 2026
**Next Review:** March 9, 2027
