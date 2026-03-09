# StorageRationalizer Access Control Policy

**Purpose:** Define who can access, modify, review, and deploy code. Enforce least-privilege principle.

**Effective Date:** March 9, 2026
**Last Updated:** March 9, 2026
**Approval Authority:** Security Team + Project Lead

---

## 1. Access Tiers

### Tier 1: Public (No Authentication Required)
- **Who:** Anyone
- **Access:** Read-only
- **Resources:**
  - Public GitHub repository (README, documentation)
  - Published releases
  - Security advisories (GitHub)

### Tier 2: Developer (Authentication Required)
- **Who:** Active project contributors with GitHub account + SSH key
- **Access:** Read + write to feature branches, read main branch
- **Resources:**
  - GitHub repository (write to non-main branches)
  - CI/CD logs (GitHub Actions)
  - Shared documentation
- **Requirements:**
  - GitHub 2FA enabled
  - SSH key added to GitHub account
  - Signed commits enforced (see Section 4)

### Tier 3: Reviewer (Higher Authentication Required)
- **Who:** Designated security reviewers + maintainers
- **Access:** Approve PRs, merge to main, manage releases
- **Resources:**
  - All developer resources +
  - main branch (merge access)
  - Release tags
  - GitHub branch protection rules
- **Requirements:**
  - All Tier 2 requirements +
  - GitHub fine-grained personal access tokens (no classic tokens)
  - Code review approval recorded

### Tier 4: Admin (Maximum Privilege)
- **Who:** Project owner + security lead (minimal)
- **Access:** All permissions including settings, secrets, deletions
- **Resources:**
  - All reviewer resources +
  - GitHub secrets management
  - Branch protection rules
  - Deployment credentials
- **Requirements:**
  - All Tier 3 requirements +
  - Hardware security key (if available)
  - Quarterly access review

### Tier 5: CI/CD Service Account (Machine)
- **Who:** GitHub Actions automation only
- **Access:** Run tests, publish reports, conditional merge
- **Resources:**
  - Read repository
  - Run workflows
  - Merge PRs only if tests pass
- **Requirements:**
  - GitHub token stored as secret (no plaintext)
  - Scoped to minimal permissions
  - Rotate quarterly
- **Restrictions:**
  - Cannot approve PRs manually
  - Cannot create releases
  - Cannot modify branch rules

---

## 2. Repository Access Matrix

| Action | Public | Developer | Reviewer | Admin | CI/CD |
|--------|--------|-----------|----------|-------|-------|
| Read code | ✅ | ✅ | ✅ | ✅ | ✅ |
| Push feature branch | ❌ | ✅ | ✅ | ✅ | ❌ |
| Push to main | ❌ | ❌ | ✅ (via PR) | ✅ | ❌ |
| Merge PR | ❌ | ❌ | ✅ | ✅ | ✅ (if tests pass) |
| Create release tag | ❌ | ❌ | ✅ | ✅ | ❌ |
| Manage secrets | ❌ | ❌ | ❌ | ✅ | ❌ |
| Modify branch rules | ❌ | ❌ | ❌ | ✅ | ❌ |
| Delete branches | ❌ | ✅ (own only) | ✅ | ✅ | ❌ |

---

## 3. Code Review Requirements

### For ANY change to security modules:
```
Files affected:
  - tools/credentials_manager.py
  - tools/api_validators.py
  - tools/input_validators.py
  - .github/workflows/security.yml
  - .pre-commit-config.yaml
```

**Required before merge:**
1. ✅ Code review by 1+ Reviewer (Tier 3+)
2. ✅ All automated tests passing (GitHub Actions)
3. ✅ Pre-commit hooks passing (black, flake8, mypy, detect-secrets)
4. ✅ No new security warnings from SAST tools
5. ✅ Audit log updated (SECURITY_AUDIT_LOG.md)

### For other changes:
**Required before merge:**
1. ✅ All automated tests passing
2. ✅ Pre-commit hooks passing

**Recommended:**
- Code review by another developer (reduces defects)

### Branch Protection Rules (Enforced on GitHub)

```yaml
Branch: main
Rules:
  - Require pull request reviews: 1
  - Dismiss stale PR approvals: yes
  - Require status checks to pass: yes
    - GitHub Actions CI/CD
    - Pre-commit hooks
  - Include administrators: yes
  - Allow force pushes: no
  - Allow deletions: no
```

---

## 4. Commit Signing & Verification

### Requirement: All commits must be signed

#### Setup (one-time):
```bash
# Generate GPG key (if not present)
gpg --full-generate-key
# Select: RSA, 4096 bits, 1 year expiry

# Configure Git to sign commits
git config --global user.signingkey <KEY_ID>
git config --global commit.gpgsign true
git config --global tag.gpgsign true

# Verify setup
git log --show-signature -1
```

#### For each commit:
```bash
# Sign is automatic now
git commit -m "commit message"

# Or sign manually
git commit -S -m "commit message"

# Verify commits are signed
git log --oneline --show-signature
```

### GitHub Configuration:
- Enable "Require commits to be signed" on main branch
- Verify signatures in GitHub UI (commits show ✅ verified badge)

---

## 5. Credential & Secret Management

### NO Credentials in Code ❌
- **Never commit:** passwords, API keys, tokens, private keys
- **Always commit:** `requirements.txt` with package versions, `.gitignore` patterns
- **Storage:** Use `tools/credentials_manager.py` (AES-256-GCM encrypted)

### Secrets Storage Location
```
Repository:
  - .gitignore: includes "credentials/"

Encrypted storage:
  - credentials/encrypted/  ← git-ignored
  - Only accessible via CredentialManager class

GitHub Actions:
  - Use GitHub Secrets (repository → Settings → Secrets and variables)
  - Never log or echo secrets
```

### Adding a New Secret to GitHub Actions
```bash
# 1. Go to: GitHub repo → Settings → Secrets and variables → Actions
# 2. Click "New repository secret"
# 3. Name: YOUR_SECRET_NAME
# 4. Value: <paste secret value>
# 5. Click "Add secret"

# 6. Use in workflow:
# In .github/workflows/*.yml:
# env:
#   MY_SECRET: ${{ secrets.YOUR_SECRET_NAME }}
```

### Rotating Secrets
```bash
# Schedule: quarterly (every 3 months)

# 1. Generate new secret (in your credential system)
# 2. Update GitHub Secret (same process as above)
# 3. Update local credentials/ directory
# 4. Commit: "security: rotate credentials [date]"
# 5. Disable old secret in credential system
# 6. Log in SECURITY_AUDIT_LOG.md
```

---

## 6. Access Revocation

### When developer leaves or changes role:

```bash
# 1. Immediate (within 1 hour)
# - Remove SSH key from GitHub account
# - Disable personal access tokens
# - Revoke GitHub Actions token if applicable

# 2. Within 24 hours
# - Remove from GitHub team
# - Review any outstanding PRs (reassign or close)
# - Check for lingering credentials (rotate if used)

# 3. Post-exit
# - Audit git log for commits (verify legitimacy)
# - Document in SECURITY_AUDIT_LOG.md
# - Review branch protection rules

# Shell script for admin:
#!/bin/bash
USERNAME=$1
echo "Revoking access for: $USERNAME"
# (requires GitHub API token)
curl -X DELETE https://api.github.com/user/keys/<KEY_ID> \
  -H "Authorization: token $GITHUB_TOKEN"
```

---

## 7. Deployment Access Control

### Who can deploy to production?

**Tier 3+ (Reviewer/Admin) only**

**Deployment process:**
```bash
# 1. Merge approved PR to main
# 2. GitHub Actions runs full test suite
# 3. If tests pass, create git tag:
git tag -s v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3

# 4. GitHub creates release (automatic via Actions)
# 5. Deploy to production (manual or automated via CD)

# 6. Verify deployment:
./verify_issues.sh
pytest tests/ -v --cov
```

### Rollback authority:
- **Tier 3+** can roll back via `git revert`
- **Tier 1-2** can request rollback (requires Tier 3 approval within 30 min)

---

## 8. Audit & Compliance

### Monthly Access Review
```bash
# Run this monthly (first of month):

# 1. List all contributors
git log --format="%aN" | sort | uniq

# 2. Verify each is still active
# - Check GitHub user profile
# - Confirm still on team
# - If inactive: revoke access

# 3. Audit signed commits
git log --oneline --show-signature | grep -v "Good signature"

# 4. Check branch protection rules
# - Via GitHub UI: Settings → Branches → Branch protection rules

# 5. Rotate secrets
# - Check SECURITY_AUDIT_LOG.md for last rotation
# - If >90 days ago: rotate now

# 6. Document in SECURITY_AUDIT_LOG.md
# - Add row to "Access Control Changes"
```

### Annual Access Review
- [ ] Tier assignments still accurate?
- [ ] GitHub 2FA enabled for all active users?
- [ ] SSH keys rotated (>1 year old)?
- [ ] Stale access removed?
- [ ] New users added correctly?

**Sign-off:** Security Lead + Project Owner

---

## 9. Exception Process

### Need access outside of tier definition?

**Request:**
1. Create GitHub issue: "Access Request: [name] [reason]"
2. Include: justification, duration, what access needed
3. Assign to Security Lead
4. Wait for approval (required, no self-approval)

**Approval (Security Lead):**
1. Verify requester identity
2. Evaluate risk vs. benefit
3. Add comment: "APPROVED for [duration]" or "DENIED with reason"
4. Log in SECURITY_AUDIT_LOG.md

**Expiration:**
- Temporary access auto-expires after set duration
- Permanent access requires quarterly re-approval

---

## 10. Policy Enforcement

### Automated Enforcement
- ✅ Branch protection rules (GitHub enforces)
- ✅ Pre-commit hooks (local + CI/CD)
- ✅ Signed commits (GitHub enforces if configured)
- ✅ Secret detection (detect-secrets pre-commit)

### Manual Enforcement
- 🔍 Monthly audit (documented above)
- 👀 Code review (verify commit authors)
- 🔄 Access revocation (on role change)

### Non-Compliance
- **First violation:** Warning + retraining
- **Second violation:** Access revoked temporarily (1 week)
- **Pattern:** Permanent revocation + investigation

---

## 11. Sign-Off & Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Security Lead | TBD | — | March 9, 2026 |
| Project Owner | TBD | — | March 9, 2026 |
| Developer | Self-acknowledge | — | Upon first commit |

---

## 12. Updates & Review Schedule

- **Review frequency:** Annually (March 9)
- **Update triggers:** Role changes, new vulnerabilities, tooling changes
- **Version control:** Commit to main branch with tag `policy-v<N>`

---

## Appendix: GitHub Team Setup

```bash
# Create team for maintainers (Tier 3)
# In GitHub: Settings → Teams → New team
# Name: storagationalizer-maintainers
# Members: [list of reviewers]
# Permissions: Pull request review required

# Create team for admins (Tier 4)
# Name: storagationalizer-admins
# Members: [lead only]
# Permissions: Admin
```

---

## Quick Reference

**Need to grant access?**
```
Tier 1 (Public) → No action needed
Tier 2 (Developer) → Add SSH key to GitHub
Tier 3 (Reviewer) → Add to maintainers team + branch rule approval
Tier 4 (Admin) → Add to admins team (minimal)
Tier 5 (CI/CD) → Create token in GitHub Settings → Developer settings → Personal access tokens
```

**Need to revoke access?**
```
Remove → SSH key / token
Disable → GitHub 2FA
Remove from → GitHub team
Audit → git log for commits
```

**Suspicious activity?**
```
→ File GitHub Security Advisory
→ Follow INCIDENT_RESPONSE_RUNBOOK.md
→ Notify security team immediately
```
