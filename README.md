# StorageRationalizer v2

Agentic system to scan, classify, verify, and clean duplicate files across cloud storage services — consolidating everything into Google Drive.

## Goal

| Service | Before | After |
|---|---|---|
| iCloud 2TB ($9.99) | Primary storage | Downgrade to 50GB ($0.99) |
| OneDrive | Active | Cancel |
| Amazon Photos | Active | Cancel |
| Google Drive 2TB ($9.99) | Secondary | Primary — everything here |
| **Total** | **~$30+/mo** | **~$10.98/mo** |

## Architecture

```
MacBook (hub)
├── phase1/scanner.py       → scan all sources → manifest.db
├── phase2/classifier.py    → find duplicates → duplicates.db
├── phase2/verifier.py      → verify media dupes (no pHash, no Pillow)
├── phase3/cleaner.py       → delete confirmed duplicates
├── tools/tracker.py        → Flask web UI to track progress
└── tools/gphotos_test.py   → test Google Photos API connectivity
```

## Sources Scanned

| Source | Files | Size | Notes |
|---|---|---|---|
| OneDrive | 95,013 | 6.6 TB | MSAL device flow auth |
| iCloud Photos | 18,661 | 5.9 GB | osxphotos (reads Photos.app DB) |
| MacBook Local | 2,879 | 12.9 GB | Direct filesystem scan |
| Google Drive | 2,094 | 34.6 GB | Google Drive API v3 |
| iCloud Drive | 21 | 112 MB | Direct filesystem scan |
| Google Photos | — | ~250 GB | ⏳ Takeout pending |
| Amazon Photos | — | — | ⏸ Skipped |

## Phase Results

| Phase | Result |
|---|---|
| Phase 1 (Scan) | ✅ 118,668 files scanned |
| Phase 2 (Classify) | ✅ 11,006 duplicate groups, 155.6 GB recoverable |
| Phase 2b (Verify) | ✅ 809 media groups verified, 28,717 files to delete, 152.7 GB |
| Phase 3 (Clean) | ✅ Built — ready to run |

## Setup

### 1. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Credentials

Place in `credentials/`:
- `onedrive_client_id.txt` — Azure app client ID (device flow)
- `google_client_secret.json` — OAuth2 client secret (Drive + Photos)

### 3. Run Phase 1 (scan)

```bash
# Scan all sources
python3 phase1/scanner.py --source all

# Scan a specific source
python3 phase1/scanner.py --source onedrive
python3 phase1/scanner.py --source gdrive
python3 phase1/scanner.py --source icloud_photos
python3 phase1/scanner.py --source local --path ~/Documents
```

### 4. Run Phase 2 (classify duplicates)

```bash
python3 phase2/classifier.py
```

### 5. Run Phase 2b (verify media duplicates)

```bash
python3 phase2/verifier.py
```

### 6. Run Phase 3 (clean)

```bash
# Always dry-run first
python3 phase3/cleaner.py --dry-run --mode all

# Safe mode: only 100% exact-hash confirmed (96 files, ~709 MB)
python3 phase3/cleaner.py --mode safe

# Docs mode: 90%+ name+size dupes in docs/archives (26,833 files, ~140.7 GB)
python3 phase3/cleaner.py --mode docs

# All: combined (141.4 GB total)
python3 phase3/cleaner.py --mode all

# Filter by source
python3 phase3/cleaner.py --mode all --source onedrive
```

### 7. Launch tracker

```bash
python3 tools/tracker.py
# Open http://localhost:5000
```

## Keep Priority

When a duplicate exists across sources, keep in this order:

```
Google Drive > OneDrive > MacBook Local > iCloud Drive > iCloud Photos
```

## Roadmap

| Phase | What | Status |
|---|---|---|
| 1 | Scan all sources | ✅ Done |
| 2 | Classify duplicates | ✅ Done |
| 2b | Verify media duplicates | ✅ Done |
| 3 | Clean docs + 100% confirmed | ✅ Ready |
| 4 | Add Google Photos (Takeout) + Amazon (Windows) | ⏳ Pending |
| 5 | Re-scan + re-classify complete manifest | After Phase 4 |
| 6 | Clean media with full picture | After Phase 5 |
| 7 | Folder structure suggester | After Phase 6 |
| 8a | Migrate docs → Google Drive | After Phase 7 |
| 8b | Migrate photos → Google Photos | After Phase 6 |
| 9 | Verify migrations, cancel services | After Phase 8 |
| 10 | Vector DB + LLM assistant | Future |

## Google Drive Target Structure

```
My Drive/
├── Finance/
│   ├── Tax/
│   ├── Banking/
│   └── Insurance/
├── Trading/
│   ├── Research/
│   ├── Statements/
│   └── Strategies/
├── Property/
│   ├── Rental/
│   ├── Mortgages/
│   └── Maintenance/
├── Family/
│   ├── Kids/
│   ├── Medical/
│   └── Legal/
├── Work/
│   ├── Current/
│   └── Archive/
├── Tech/
│   ├── Projects/
│   └── Learning/
├── Books/
│   ├── Trading/
│   ├── Tech/
│   ├── Business/
│   └── General/
├── Photos/
└── _Inbox/
```

## Notes

- **pHash removed** — verifier uses metadata hashes (Pass 1, zero download) + 10MB partial download fallback (Pass 2). No Pillow dependency.
- **Google Photos API** is blocked for new apps — use Takeout export instead.
- **OneDrive auth** uses MSAL device flow with `consumers` authority (personal accounts).
- **iCloud Photos** scanned via `osxphotos` which reads the Photos.app SQLite database directly.
