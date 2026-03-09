# StorageRationalizer — Project Context Summary

**Purpose:** Single authoritative reference consolidating all project decisions,
roadmap phases, financial targets, deduplication strategies, and architecture context.

**Compiled from:** Full audit of all 16 docs + 10 source files (March 9, 2026)
**Status:** Phase 3/3 complete — Extended Testing begins Q2 2026

---

## 1. Project Goal

Eliminate redundant cloud storage subscriptions by deduplicating files across all
6 sources and consolidating everything into Google Drive as the single primary store.

**Before → After:**

| Service | Before | After | Savings |
|---------|--------|-------|---------|
| iCloud Drive 2TB | $9.99/mo | $0.99/mo (50GB plan) | $9.00/mo |
| OneDrive | ~$X/mo | $0.00 (cancelled) | $X/mo |
| Amazon Photos | ~$X/mo | $0.00 (cancelled) | $X/mo |
| Google Drive 2TB | $9.99/mo | $9.99/mo (primary) | $0.00 |
| **Total** | **~$30+/mo** | **~$10.98/mo** | **~$19+/mo** |

**Project is COMPLETE when:** `tools/financial_tracker.py --savings` shows total ≤ $10.98/mo.

---

## 2. Phase Roadmap

> **CLARIFICATION:** There is no formal "10-phase" roadmap in any document.
> The project has 3 operational phases (complete) and 3 extended testing phases (planned).
> Total: 6 phases.

### Operational Phases (COMPLETE)

#### Phase 1 — File Discovery & Database
**File:** `phase1/scanner.py` (1,064 lines)

Scans all 6 sources and writes every file record to `manifests/manifest.db`:

| Source | Access Method | Priority Weight |
|--------|---------------|-----------------|
| Google Drive | Google Drive API v3 | 1 (highest — future primary) |
| OneDrive | Microsoft Graph API | 2 |
| MacBook Local | Filesystem walk | 3 |
| iCloud Drive | Filesystem walk (`~/Library/Mobile Documents/`) | 4 |
| iCloud Photos | osxphotos (reads Photos.app SQLite DB) | 5 |
| Google Photos | Photos Library API | 6 (lowest) |

**Key CLI flags:**
```bash
python3 phase1/scanner.py --source all        # scan all sources
python3 phase1/scanner.py --source google_drive
python3 phase1/scanner.py --dry-run
```

---

#### Phase 2a — Duplicate Classification
**File:** `phase2/classifier.py` (1,063 lines)

Compares every file against manifest, assigns duplicate group + confidence score.

**Confidence tiers:**

| Score | Meaning | Method |
|-------|---------|--------|
| 100% | Byte-for-byte identical | Full SHA-256 match |
| 95% | Visually identical | Perceptual hash (pHash) ≤10 hamming distance |
| 90% | Likely identical | First 10MB partial hash match |
| 40% | Name/size match only | Heuristic — needs human review |

**Output:** `manifests/duplicates.db` with `duplicate_groups` and `duplicate_members` tables.

---

#### Phase 2b — Media Verification (pHash)
**File:** `phase2/verifier.py` (644 lines)

**Status: FULLY IMPLEMENTED** — pHash is not pending, it exists now.

Verification layers (run in order, stop at first confident match):
1. Partial hash (first 10MB SHA-256) — fast filter
2. Full hash if partial matches — confirms byte identity
3. pHash — catches same photo in different format/quality/compression
4. Human review queue — pHash-similar but not identical (hamming 5–15)

**pHash implementation:**
```python
def phash_local(path: str) -> Optional[str]:
    """Perceptual hash via PIL — resize to 8x8 grayscale, hash pixel values."""
    from PIL import Image
    # Returns 64-bit hex string; hamming distance < 10 = visually same photo

def phash_distance(h1: str, h2: str) -> int:
    """Hamming distance between two hashes. < 10 = visually similar."""
```

**Dependency:** Requires `Pillow` (PIL) — optional, gracefully skips if not installed.

**CLI:**
```bash
python3 phase2/verifier.py --phash           # enable perceptual hashing
python3 phase2/verifier.py --source onedrive
```

---

#### Phase 3 — Safe Cleanup
**File:** `phase3/cleaner.py` (746 lines)

Deletes confirmed duplicates. All deletions are reversible (moved to cloud/local trash).

**Modes:**

| Mode | Confidence | File Types | Scope |
|------|-----------|------------|-------|
| `--mode safe` | 100% | All types | ~96 files, ~709MB |
| `--mode docs` | ≥90% | Docs/archives only (no photos/videos) | ~26,833 files, ~140.7GB |
| `--mode all` | Both above | Combined | ~141.4GB |

**Recovery windows:**
- MacBook Local → `.Trash` (indefinite)
- OneDrive → Recycle Bin (30 days)
- Google Drive → Trash (30 days)
- iCloud Photos → Recently Deleted (30 days)

**Always dry-run first:**
```bash
python3 phase3/cleaner.py --mode safe --dry-run
python3 phase3/cleaner.py --mode safe --run      # only after reviewing dry-run
```

---

### Extended Testing Phases (PLANNED — Q2-Q3 2026)

#### Phase 4 — Integration Testing (Q2 2026)
**Target:** 50+ new tests
- Mock OneDrive/Google Drive API calls
- Credential manager with real crypto
- File operations with symlinks
- End-to-end restore scenarios

**Status:** Test stubs exist in `tests/integration/`

---

#### Phase 5 — Performance Testing (Q2 2026)
**Target:** 20+ tests
- Throughput: 1,000 credential accesses/sec
- Concurrency: 10 threads accessing credential store
- Load: 100+ files, 10,000+ credentials

**Status:** Test stubs exist in `tests/performance/`

---

#### Phase 6 — Security / Penetration Testing (Q3 2026)
**Target:** 60+ tests
- 50+ shell/AppleScript injection payloads
- CVE scanning via Dependabot
- Manual TOCTOU race condition audit

**Status:** Test stubs exist in `tests/security/`

**Overall target by August 2026:** 150+ tests, ≥95% coverage

---

## 3. Deduplication Strategy (Full Detail)

### Detection Pipeline

```
manifest.db (all files)
    ↓
classifier.py — group exact name+size matches
    ↓
verifier.py — confirm identity:
    1. Partial hash (fast)
    2. Full hash (definitive)
    3. pHash (visual — photos/videos only)
    4. Human review queue (pHash edge cases)
    ↓
duplicates.db (grouped with confidence + keep_file_id)
    ↓
cleaner.py — delete non-keep copies (recovery bins)
```

### Keep-File Selection

Within each duplicate group, the file to KEEP is chosen by source priority:
1. Google Drive copy → always keep (destination)
2. OneDrive copy → keep if no Google Drive copy
3. MacBook Local → keep if no cloud copies
4. iCloud Drive → lower priority
5. iCloud Photos → lowest priority

### Re-scan Strategy (Quarterly Maintenance)

```bash
# Re-scan all sources (new files since last run)
python3 phase1/scanner.py --source all

# Re-classify with enriched metadata
python3 phase2/classifier.py

# Preview new cleanup opportunities
python3 phase3/cleaner.py --mode safe --dry-run
```

**Schedule:** Quarterly (see `docs/MAINTENANCE_SCHEDULE.md` + `cron_jobs.sh`)

---

## 4. Metadata Enrichment (PENDING DESIGN)

**Status:** Design document exists (`docs/METADATA_ENRICHMENT_DESIGN.md`).
Implementation does NOT exist — `tools/enricher.py` has not been created.

### What It Is

Augmenting file records in `manifest.db` with additional computed/sourced fields
to enable more accurate duplicate detection and smarter keep-file selection.

### Proposed Fields

| Field | Source | Description | Priority | Needed For |
|-------|--------|-------------|----------|------------|
| `content_hash` | Computed | Full file SHA-256 | HIGH | Exact dedup |
| `perceptual_hash` | PIL/pHash | Visual similarity hash | MEDIUM | Photo dedup |
| `exif_datetime` | EXIF | True capture date | HIGH | Sort by date, not filename |
| `camera_model` | EXIF | Camera that took photo | LOW | Prefer higher-quality source |
| `location_name` | Reverse geocode | GPS coords → city name | LOW | Metadata display |
| `album_memberships` | Google Photos API | Which albums contain file | MEDIUM | Preserve album associations |
| `cloud_last_modified` | Drive API | Server-side modified time | MEDIUM | Prefer most recently edited |
| `is_shared` | Drive API | Shared with others? | HIGH | Never delete shared files |
| `download_count` | Drive API | Usage frequency | LOW | Retention heuristic |

### Architecture (Proposed)

```
manifest.db (existing scanner output)
    ↓
tools/enricher.py (NOT YET CREATED)
    ↓
manifest.db (with enriched columns added)
    ↓
phase2/classifier.py (uses enriched fields → better dedup confidence)
```

### When Does Enrichment Run?

**Proposed:** After Phase 1 (scanner), before Phase 2 (classifier).

```bash
# Proposed workflow (once enricher.py exists):
python3 phase1/scanner.py       # discover files
python3 tools/enricher.py       # enrich metadata
python3 phase2/classifier.py    # classify with enriched data
python3 phase3/cleaner.py       # clean with confidence
```

### Open Questions (PENDING USER DECISION)

1. Scope — all files or photos/videos only?
2. Large files — full SHA-256 or quick_xor for >1GB files?
3. pHash library — Pillow is already in verifier.py, acceptable as hard dep?
4. Google Photos albums API — requires additional OAuth scope?
5. Incremental enrichment — re-enrich all files or only new ones per run?
6. `is_shared` check — must never delete shared files: block in cleaner.py?

**Note:** `perceptual_hash` is ALREADY computed in `phase2/verifier.py` for verification.
Enrichment would persist it to `manifest.db` for use in classifier.

---

## 5. Dashboard & Tracker Architecture

### Web UI (FULLY IMPLEMENTED)

**Backend:** `tools/tracker.py` (Flask, ~400 lines)
**Frontend:** `tools/templates/tracker.html` (78,649 bytes — large, feature-rich HTML)
**Database:** `tools/tracker_data.db` (SQLite, auto-created)

**Run:**
```bash
python3 tools/tracker.py
# Open: http://localhost:5000
```

**What the dashboard tracks:**

| Section | Content |
|---------|---------|
| Storage Progress | GB cleaned per source, target: 143GB |
| Financial | Monthly cost per subscription, savings to date |
| Phase Status | Phase 1/2/3 completion checkmarks |
| Checklist | Per-item task tracking |
| Notes | Per-section markdown notes |
| Rollback | Links to restore operations |

**DB Schema:**
```sql
fields    — key/value store for numeric progress metrics
notes     — section → markdown content
checklist — item_id → checked (0/1)
```

**API Endpoints** (Flask routes in `tracker.py`):
- `GET /` — serve tracker.html
- `GET /api/status` — return all field values as JSON
- `POST /api/update` — update a field value
- `POST /api/notes` — save section notes
- `POST /api/checklist` — toggle checklist item

### Financial Tracker (STUB)

**File:** `tools/financial_tracker.py`
**Database:** `manifests/financial_tracker.db`

**CLI:**
```bash
python3 tools/financial_tracker.py --status    # current cost status
python3 tools/financial_tracker.py --snapshot  # record monthly snapshot (manual entry)
python3 tools/financial_tracker.py --savings   # savings vs baseline
```

**Current limitation:** Snapshots require manual entry — no live API queries yet.

---

## 6. API Quota Monitoring

**File:** `tools/api_monitor.py`
**Database:** `manifests/api_usage.db`
**Docs:** `docs/API_USAGE_MONITORING.md`

### Quotas

| Service | Limit | Alert Threshold |
|---------|-------|-----------------|
| Google Drive | 1B units/day, 1000 req/100s | 80% daily, 70% rate |
| OneDrive | 10,000 req/10min | 70% rate |

### Google Drive Quota Costs

| Operation | Units |
|-----------|-------|
| `files.list`, `files.get` | 1 unit |
| `files.create`, `files.update` | 10 units |
| `files.delete` | 30 units |
| `files.copy` | 100 units |

### Usage

```python
from tools.api_monitor import APIMonitor
monitor = APIMonitor()

with monitor.track("google_drive", "files.list"):
    results = service.files().list(...).execute()

monitor.report()        # usage summary
monitor.check_alerts()  # check thresholds
```

**Integration status:**
- [x] `tools/api_monitor.py` — implemented
- [ ] Integrated into `phase1/scanner.py` — pending
- [ ] Integrated into `phase3/cleaner.py` — pending

---

## 7. Security Architecture (All 3 Issues Fixed)

| Issue | Vulnerability | Fix | File | Tests |
|-------|--------------|-----|------|-------|
| #1 | Credentials stored in plaintext | AES-256-GCM + PBKDF2 | `tools/credentials_manager.py` | 22 integration |
| #2 | Silent API failures | Strict response schema validation | `tools/api_validators.py` | 13 unit + 27 integration |
| #3 | AppleScript/shell injection | Input sanitization + `shell=False` | `tools/input_validators.py` | 36 unit + 40 integration |

---

## 8. Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** | **FULLY SUPPORTED** | Primary target; uses osxphotos, AppleScript, macOS Trash |
| Windows | NOT IMPLEMENTED | Mentioned once in MASTER_SETUP_GUIDE.md as future aspiration |
| Linux | NOT TESTED | No Linux-specific code; osxphotos is macOS-only |

**macOS-specific dependencies:**
- `osxphotos` — reads Photos.app database
- `pyobjc-*` — macOS Objective-C bridge
- AppleScript via `subprocess` with `shell=False` — Finder "Put Back" for trash restore

---

## 9. Cloud & Service Integration

| Service | Integrated | Purpose | API Used |
|---------|-----------|---------|----------|
| Google Drive | ✅ | Primary destination + source | Google Drive API v3 |
| Google Photos | ✅ | Source (scan only) | Photos Library API |
| OneDrive | ✅ | Source + delete | Microsoft Graph API |
| iCloud Drive | ✅ | Source (filesystem only) | Filesystem walk |
| iCloud Photos | ✅ | Source (scan + delete) | osxphotos library |
| MacBook Local | ✅ | Source + delete | Filesystem + macOS Trash |
| Amazon Photos | ❌ | NOT INTEGRATED | Cost target only |
| Amazon S3/Drive | ❌ | NOT INTEGRATED | Not planned |

**Amazon Photos:** Listed in `docs/FINANCIAL_TARGETS.md` as a subscription to cancel,
but there is no Amazon Photos API integration in the codebase. Manual cancellation expected.

---

## 10. Key Decisions & Constraints

| Decision | Value | Rationale |
|----------|-------|-----------|
| Primary destination | Google Drive 2TB | Keep existing $9.99/mo plan as sole storage |
| Never delete from Google Drive | ENFORCED | It's the destination; deleting defeats the purpose |
| Always dry-run before cleanup | ENFORCED | Irreversibility risk |
| Confidence threshold for auto-delete | 90%+ (safe mode), 100% (safest) | Balances thoroughness vs risk |
| Credential storage | AES-256-GCM on disk | No plaintext, no env vars |
| Shell execution | `shell=False` always | Prevents injection |
| Python version | 3.11+ | Type hints, match statements |
| macOS version | 12.0+ | osxphotos requirement |
| pHash library | Pillow (PIL) — optional | Skip gracefully if not installed |
| Git commits | Signed (GPG) | Audit trail integrity |
| Dependency versions | Pinned exact (`==`) | Reproducible builds |

---

## 11. File Map — Key Files Only

```
StorageRationalizer/
├── phase1/scanner.py           # Scan 6 sources → manifest.db
├── phase2/classifier.py        # Find duplicates → duplicates.db
├── phase2/verifier.py          # Verify via hash + pHash
├── phase3/cleaner.py           # Delete non-keep copies (safe, recovery bins)
│
├── tools/
│   ├── credentials_manager.py  # AES-256-GCM credential store
│   ├── api_validators.py       # OneDrive/GDrive response validation
│   ├── input_validators.py     # Path/AppleScript injection prevention
│   ├── rollback.py             # Restore from trash/recycle bin
│   ├── tracker.py              # Flask dashboard (http://localhost:5000)
│   ├── verify_cleanup.py       # Cross-reference cleanup log vs duplicates.db
│   ├── financial_tracker.py    # Monthly cost snapshot CLI (STUB)
│   ├── api_monitor.py          # Quota tracking + alerts
│   └── templates/tracker.html  # Dashboard frontend (78KB)
│
├── config/logging_config.py    # Rotating log handlers (app/security/api/file_ops)
├── manifests/                  # manifest.db, duplicates.db, rollback.db (gitignored)
├── logs/                       # app.log, security.log, api.log, file_operations.log
├── credentials/encrypted/      # Encrypted service credentials (gitignored)
│
├── tests/
│   ├── test_api_validators.py      # 13 unit tests (92% coverage)
│   ├── test_input_validators.py    # 36 unit tests (98% coverage)
│   ├── test_rollback.py            # 10 stubs (skipped)
│   ├── test_tracker.py             # 10 stubs (skipped)
│   ├── test_verify_cleanup.py      # 5 real + 5 stubs
│   ├── integration/                # 106 integration tests
│   ├── performance/                # 18 performance tests
│   └── security/                   # 47 security/pen tests
│
└── docs/
    ├── PROJECT_CONTEXT_SUMMARY.md  # THIS FILE
    ├── FINANCIAL_TARGETS.md        # Cost savings goals + monthly tracking
    ├── METADATA_ENRICHMENT_DESIGN.md  # Enrichment design (PENDING user input)
    ├── API_USAGE_MONITORING.md     # Quota + cost monitoring
    ├── DEPLOYMENT_GUIDE.md         # Local macOS setup
    ├── MAINTENANCE_SCHEDULE.md     # Weekly/monthly/quarterly tasks
    ├── EXTENDED_TESTING_PLAN.md    # Phase 4-6 test roadmap
    ├── SECURITY_AUDIT_LOG.md       # Compliance trail
    ├── INCIDENT_RESPONSE_RUNBOOK.md
    ├── ACCESS_CONTROL_POLICY.md
    ├── DEPENDENCY_MANAGEMENT_PLAN.md
    ├── MONITORING_AND_ALERTING.md
    ├── MASTER_SETUP_GUIDE.md
    ├── SECURITY_REMEDIATION_COMPLETION_REPORT.md
    └── CRITICAL_ISSUE_2_API_RESPONSE_VALIDATION_DESIGN.md
```

---

## 12. What Does NOT Exist (Common Misconceptions)

| Item | Reality |
|------|---------|
| "10-phase roadmap" | No such document. 3 operational phases + 3 testing phases = 6 total |
| Windows support | 0% implemented; one aspirational mention in MASTER_SETUP_GUIDE.md |
| Amazon Photos integration | Not integrated; listed as subscription to cancel manually |
| `tools/enricher.py` | Does NOT exist — metadata enrichment is design-only |
| Live financial API queries | `financial_tracker.py` is manual-entry only (stub) |
| pHash as "future work" | WRONG — pHash is already implemented in `phase2/verifier.py` |
| Cloud deployment | This is a local macOS CLI tool; "production" = reliable local setup |

---

*Last updated: March 9, 2026 — compiled from full audit of 16 docs + 10 source files*
