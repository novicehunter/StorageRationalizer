# Financial Targets — StorageRationalizer

**Purpose:** Track subscription cost reduction goals and actual savings.
**Status:** TRACKING — update monthly after each cleanup run
**Owner:** User
**Last Updated:** March 9, 2026

---

## Target State

| Service | Before | After | Monthly Savings |
|---------|--------|-------|-----------------|
| iCloud Drive (2TB) | $9.99/mo | $0.99/mo (50GB) | $9.00 |
| OneDrive | $X.XX/mo | $0.00 (cancelled) | $X.XX |
| Amazon Photos | $X.XX/mo | $0.00 (cancelled) | $X.XX |
| Google Drive (2TB) | $9.99/mo | $9.99/mo (primary) | $0.00 |
| **Total** | **~$30+/mo** | **~$10.98/mo** | **~$19+/mo** |

---

## Progress Tracker

| Month | iCloud Size | OneDrive Size | GDrive Size | Active Subs | Monthly Cost |
|-------|-------------|---------------|-------------|-------------|--------------|
| Feb 2026 (baseline) | ? GB | ? GB | ? GB | iCloud+OneDrive+Amazon+GDrive | ~$30+/mo |
| Mar 2026 | — | — | — | — | — |
| Apr 2026 | — | — | — | — | — |
| May 2026 | — | — | — | — | — |

> Fill in actual values after each cleanup run using `tools/financial_tracker.py`.

---

## Milestones

- [ ] **Milestone 1:** iCloud reduced below 50GB → downgrade to $0.99/mo plan
- [ ] **Milestone 2:** OneDrive confirmed empty → cancel subscription
- [ ] **Milestone 3:** Amazon Photos confirmed empty → cancel subscription
- [ ] **Milestone 4:** Google Drive is sole primary storage → DONE
- [ ] **Milestone 5:** Total monthly cost ≤ $10.98 → PROJECT COMPLETE

---

## Tracking Tool

See `tools/financial_tracker.py` for automated tracking.

```bash
# Check current storage usage across all services
python3 tools/financial_tracker.py --status

# Log a monthly snapshot
python3 tools/financial_tracker.py --snapshot

# Show savings to date
python3 tools/financial_tracker.py --savings
```
