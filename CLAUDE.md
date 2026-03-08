# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

StorageRationalizer is a storage rationalization tool that consolidates duplicate files across cloud services into Google Drive. Phase 1 scans cloud sources into `manifest.db`, Phase 2 classifies duplicates into `duplicates.db`, Phase 2b verifies media dupes via partial hash, and Phase 3 deletes confirmed duplicates.

**Keep priority:** Google Drive > OneDrive > MacBook Local > iCloud Drive > iCloud Photos

**Rules:**
- Never delete from Google Drive — it is the migration target.
- Always dry-run (`--dry-run`) before executing any cleanup.
- After every file edit or script run that produces output, commit all changes and push to origin main. Commit format: `phase[N]: [what changed]` (e.g. `phase3: exclude google_drive from cleaner mode all`).
- **Google Drive has 207 files flagged as duplicates — do NOT delete these yet.** They will be cleaned up in Phase 7/8 when we reorganize Google Drive into the target folder structure.
- **Phase 3 cleanup runs with `--source onedrive`, `--source macbook_local`, `--source icloud_photos`, `--source icloud_drive` ONLY. Never `--source google_drive`.**

**Permissions — proceed without asking:**
- Reading any file in the repo
- Running Python scripts (`python3 phase*/...`, `tools/...`)
- Checking logs (`logs/`, `tail`, `grep` on log files)
- Querying SQLite databases (`manifest.db`, `duplicates.db`)
- `git status`, `git diff`, `git add`, `git commit`, `git push`

**Permissions — always ask first:**
- Deleting local files or directories
- API calls that modify cloud data (OneDrive delete, Google Drive trash, iCloud Photos delete)
- Installing packages (`pip install`, `brew install`)
- `git push --force` or any destructive git operation

## Commands

```bash
# Install dependencies
pip3 install -r requirements.txt

# Phase 1 — Scan sources into manifest.db
python3 phase1/scanner.py                          # all sources
python3 phase1/scanner.py --sources local icloud_drive
python3 phase1/scanner.py --reset                  # wipe and restart

# Phase 2 — Find duplicates → duplicates.db + reports/
python3 phase2/classifier.py
python3 phase2/classifier.py --min-confidence 80 --sources onedrive icloud_photos

# Phase 2b — Verify 90% media duplicates (partial hash)
python3 phase2/verifier.py
python3 phase2/verifier.py --dry-run --source onedrive

# Phase 3 — Delete confirmed duplicates (ALWAYS dry-run first)
python3 phase3/cleaner.py --dry-run --mode all
python3 phase3/cleaner.py --mode safe              # 100% exact-hash only
python3 phase3/cleaner.py --mode docs              # 90%+ docs/archives, no media
python3 phase3/cleaner.py --mode all --source onedrive

# Tracker UI
python3 tools/tracker.py                           # opens http://localhost:5000
```

There is no test suite. To exercise individual logic, import functions directly from each module.

## Architecture

The pipeline is linear — each phase depends on the previous phase's SQLite database output.

```
phase1/scanner.py   →  manifests/manifest.db
phase2/classifier.py →  manifests/duplicates.db  +  reports/
phase2/verifier.py  →  updates duplicates.db confidence scores in place
phase3/cleaner.py   →  reads duplicates.db, deletes files, marks manifest
```

### Data model

**`manifest.db` — `files` table**: One row per file across all sources. Key columns: `file_id` (UUID), `source`, `source_path` (local files), `cloud_file_id` (cloud files), `sha256_hash`, `md5_hash`, `filename`, `file_size`, `is_photo/is_video/is_document`, `is_downloaded`.

**`duplicates.db`**: Two tables — `duplicate_groups` (one row per duplicate cluster with `confidence`, `match_type`, `wasted_size`, `keep_file_id`) and `duplicate_members` (each file in a group with `action='keep'|'delete'|'deleted'`).

### Source identifiers

Files are identified by `source` string:
- `macbook_local`, `icloud_drive` — local filesystem, identified by `source_path`
- `icloud_photos` — via `osxphotos`, identified by `cloud_file_id` (UUID from Photos.app)
- `google_drive`, `google_photos`, `onedrive` — cloud-only, identified by `cloud_file_id`

### Confidence levels

| Score | Meaning |
|-------|---------|
| 100 | Exact hash match (or verified by verifier) |
| 95 | pHash visual match |
| 90 | Same filename + size + date (cross-source) |
| 70 | Same filename + size |
| 50 | Same filename only |
| 40 | Verifier rejected — hashes don't match |

Phase 3 `--mode safe` acts on 100% only. `--mode docs` acts on 90%+ non-media. Media is only deleted when confidence=100 (verifier confirmed).

### Keep priority

When a file exists in multiple sources, the classifier keeps the copy in the highest-priority source:
```
Google Drive (1) > OneDrive (2) > MacBook Local (3) > iCloud Drive (4) > iCloud Photos (5)
```

### Credentials

Place in `credentials/`:
- `google_credentials.json` — Google OAuth2 client secret (Drive + Photos)
- `google_token.json` — auto-generated after first auth
- `onedrive_credentials.txt` — `CLIENT_ID=`, `TENANT_ID=`, `CLIENT_SECRET=` (key=value format)
- `onedrive_token.json` — auto-generated after first auth

### Key notes

- **iCloud Photos** is read via `osxphotos` which reads the Photos.app SQLite DB directly — no download needed for metadata.
- **Google Photos API** is blocked for new apps — use Takeout export as a workaround.
- **OneDrive auth** uses MSAL device flow with `consumers` authority (personal accounts).
- Phase 3 never permanently deletes — local files go to macOS Trash, cloud files go to provider recycle bins (30-day recovery window).
- Files >500MB skip SHA256 hashing during scan.
- The verifier downloads only the first 10MB (partial hash) to verify 90% confidence media groups before upgrading/downgrading confidence.

## Roadmap

### Phase 7/8 — Google Drive Reorganization
- Reorganize Google Drive into target folder structure.
- Clean up the 207 Google Drive files currently flagged as duplicates (held back from Phase 3).

### Phase 9.5 — Metadata Enrichment
Extend `manifest.db` with additional tables for rich personal intelligence:
- `tags` table — user-defined and auto-generated tags per file
- `entities` table — people, places, organizations extracted from file content
- `topics` table — topic clusters per file
- `relationships` table — links between files (e.g. email → attachment, photo → album)
- `embeddings` table — vector embeddings for semantic search

### Phase 10a — Personal Intelligence: Semantic Search + LLM Q&A
- Build semantic search across all personal data using embeddings from Phase 9.5.
- LLM Q&A interface: ask natural-language questions answered from your own files.

### Phase 10b — Autonomous Scheduled Agent + Digest Reports
- Autonomous scheduled agent runs on a cron/timer.
- Produces digest reports summarizing new files, storage trends, and suggested actions.
- Agent can flag anomalies, suggest cleanups, and track filing health over time.

## End State Vision

**Device roles:**
- MacBook and Windows keep active working files only.
- Google Drive is the master archive — single source of truth for all personal data.
- All devices mirror the same target folder structure.

**Phone sync:**
- iPhone Camera Roll → Google Photos auto-backup (primary).
- iCloud stays at 50GB free tier only — no iCloud Drive expansion.
