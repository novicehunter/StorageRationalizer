# Maintenance Schedule

**Status:** DOCUMENTED — cron setup pending (see cron_jobs.sh)
**Created:** March 9, 2026
**Owner:** User / Operations

---

## Recurring Tasks

### Weekly (Every Sunday)
| Task | Command | Purpose |
|------|---------|---------|
| Run security tests | `pytest tests/security/ -v` | Catch regressions |
| Check dependency CVEs | `safety check` | Supply chain security |
| Review security.log | `tail -100 logs/security.log` | Spot anomalies |

### Monthly (1st of each month)
| Task | Command | Purpose |
|------|---------|---------|
| Full test suite | `pytest tests/ -v --cov` | Confirm 346+ tests pass |
| Dependency audit | `pip list --outdated` | Identify stale packages |
| Update dependencies | See DEPENDENCY_MANAGEMENT_PLAN.md | Keep versions current |
| Financial snapshot | `python3 tools/financial_tracker.py --snapshot` | Track cost savings |
| Rotate encryption key | Manual — see credentials_manager.py | Security hygiene |
| Review audit log | `docs/SECURITY_AUDIT_LOG.md` | Update compliance trail |
| Rotate logs | `find logs -name "*.log" -mtime +30 -delete` | Disk management |

### Quarterly (Jan, Apr, Jul, Oct)
| Task | Action | Purpose |
|------|--------|---------|
| Re-scan all sources | `python3 phase1/scanner.py` | Refresh manifest |
| Re-classify duplicates | `python3 phase2/classifier.py` | Update dedup results |
| Review cleanup opportunities | `python3 phase3/cleaner.py --mode safe --dry-run` | Identify new savings |
| Security penetration test | `pytest tests/security/ -v` | Validate hardening |
| Review governance docs | All docs in docs/ | Keep docs accurate |

### Annual
| Task | Action | Purpose |
|------|--------|---------|
| Full security audit | External review | Compliance |
| Dependency major version upgrades | Manual | Stay current |
| Review financial targets | `docs/FINANCIAL_TARGETS.md` | Adjust goals |
| Archive old logs | `tar -czf logs_archive_YYYY.tar.gz logs/` | Disk management |

---

## Automated Setup

See `cron_jobs.sh` for cron configuration.

```bash
# Install cron jobs
bash cron_jobs.sh --install

# View current cron jobs
crontab -l

# Remove cron jobs
bash cron_jobs.sh --uninstall
```

---

## Status

- [ ] Weekly security tests — cron configured?
- [ ] Monthly dependency audit — automated?
- [ ] Quarterly rescan — scheduled?
- [ ] Log rotation — configured?

**Action required:** Run `bash cron_jobs.sh --install` to activate automation.
