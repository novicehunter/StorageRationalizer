# API Usage Monitoring

**Purpose:** Track token/quota consumption and costs for Google Drive and OneDrive APIs.
**Created:** March 9, 2026
**Implementation:** `tools/api_monitor.py`

---

## Overview

StorageRationalizer makes API calls to:
- **Google Drive API v3** — file listing, metadata, deletion (quota: 1B units/day)
- **Microsoft Graph / OneDrive** — file restore, metadata (quota: 10K req/10min)

The `APIMonitor` class wraps all API calls to:
1. Count quota unit consumption
2. Measure latency
3. Detect rate limit approach
4. Persist history to `manifests/api_usage.db`
5. Fire alerts at configurable thresholds

---

## Quick Start

```python
from tools.api_monitor import APIMonitor

monitor = APIMonitor()

# Wrap any API call
with monitor.track("google_drive", "files.list"):
    results = service.files().list(pageSize=100).execute()

# Or use as a decorator
@monitor.track_call("onedrive", "restore")
def restore_file(file_id):
    return graph_client.post(f"/me/drive/items/{file_id}/restore")

# Report usage
print(monitor.report())

# Check alerts
alerts = monitor.check_alerts()
```

---

## Quota Limits

### Google Drive API v3

| Operation | Quota Units | Daily Limit |
|-----------|-------------|-------------|
| `files.list` | 1 unit | 1,000,000,000 units/day |
| `files.get` | 1 unit | ↑ |
| `files.create` | 10 units | ↑ |
| `files.delete` | 30 units | ↑ |
| `files.update` | 10 units | ↑ |
| `files.copy` | 100 units | ↑ |
| Rate limit | — | 1,000 req/100s/user |

### OneDrive / Microsoft Graph

| Limit | Value |
|-------|-------|
| Rate limit | 10,000 req/10min/app |
| Throttling response | HTTP 429 with Retry-After header |

---

## Alert Thresholds

| Alert | Threshold | Action |
|-------|-----------|--------|
| Google Drive quota | >80% daily units | Log WARNING to `logs/api.log` |
| Google Drive rate | >70% of 1000 req/100s | Log WARNING |
| OneDrive rate | >70% of 10K req/10min | Log WARNING |
| Any API error | Any 4xx/5xx response | Log WARNING immediately |

---

## Integration Points

Integrate `APIMonitor` into existing modules:

```python
# In phase1/scanner.py — wrap Google Drive API calls
from tools.api_monitor import get_monitor
monitor = get_monitor()

with monitor.track("google_drive", "files.list"):
    response = service.files().list(...).execute()

# In phase3/cleaner.py — wrap OneDrive delete calls
with monitor.track("onedrive", "items.delete"):
    graph_client.delete(f"/me/drive/items/{file_id}")
```

---

## Database Schema

**File:** `manifests/api_usage.db`

```sql
CREATE TABLE api_calls (
    id           INTEGER PRIMARY KEY,
    service      TEXT NOT NULL,     -- 'google_drive' | 'onedrive'
    operation    TEXT NOT NULL,     -- e.g. 'files.list'
    started_at   TEXT NOT NULL,     -- ISO 8601 UTC
    duration_ms  REAL,              -- call latency
    quota_units  INTEGER,           -- units consumed
    status       TEXT,              -- 'ok' | 'error'
    error        TEXT               -- error message if status='error'
);
```

---

## CLI Usage

```bash
# Show summary of all API usage
python3 tools/api_monitor.py report

# Check alert thresholds
python3 tools/api_monitor.py alerts

# Show 20 most recent calls
python3 tools/api_monitor.py recent --limit 20
```

---

## Cost Estimation

Google Drive API is free within quota. Costs arise from:
- **iCloud subscription** — reduced from $9.99 → $0.99 after dedup
- **OneDrive subscription** — cancelled after migration
- **Google Drive** — $9.99/mo (stays as primary)

Track actual cost savings via `tools/financial_tracker.py`.

---

## Status

- [x] `tools/api_monitor.py` — implemented
- [x] `manifests/api_usage.db` — auto-created on first call
- [ ] Integration into `phase1/scanner.py` — pending
- [ ] Integration into `phase3/cleaner.py` — pending
- [ ] Slack/email alerts — pending (see MONITORING_AND_ALERTING.md)
- [ ] Grafana/dashboard — out of scope for local tool
