# Deployment Guide

**Status:** STUB — implementation pending
**Created:** March 9, 2026
**Owner:** DevOps / User

> This tool runs locally on macOS — "production deployment" means setting up a reliable,
> repeatable local run environment. There is no server or cloud deployment.

---

## What "Production Ready" Means Here

StorageRationalizer is a **local macOS CLI tool**. "Production deployment" means:
1. All dependencies installed and pinned
2. Credentials encrypted and stored
3. Pre-commit hooks enabled
4. Scheduled runs configured (optional)
5. Monitoring/logging active

---

## Prerequisites

- macOS 12.0+
- Python 3.11+
- OneDrive desktop app installed (for local file access)
- Google Drive desktop app installed (for local file access)
- API credentials for Google Drive, OneDrive (see docs/MASTER_SETUP_GUIDE.md)

---

## Installation Steps

```bash
# 1. Clone repository
git clone https://github.com/novicehunter/StorageRationalizer.git
cd StorageRationalizer

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install pinned dependencies
pip install -r requirements.txt

# 4. Install pre-commit hooks
pre-commit install

# 5. Set up credentials (interactive — requires master password)
python3 tools/credentials_manager.py save google client_id YOUR_CLIENT_ID
python3 tools/credentials_manager.py save google client_secret YOUR_CLIENT_SECRET
python3 tools/credentials_manager.py save onedrive client_id YOUR_CLIENT_ID

# 6. Verify security setup
./verify_issues.sh

# 7. Run tests to confirm everything works
pytest tests/ -v --cov=tools
```

---

## First Run (Dry Run)

```bash
# Phase 1: Scan all sources
python3 phase1/scanner.py --dry-run

# Phase 2: Classify duplicates
python3 phase2/classifier.py --dry-run

# Phase 3: Preview cleanup (NEVER skip dry-run)
python3 phase3/cleaner.py --mode safe --dry-run
```

---

## Production Run

```bash
# Only after dry-run review:
python3 phase3/cleaner.py --mode safe --run

# Verify cleanup
python3 tools/verify_cleanup.py

# Rollback if needed
python3 tools/rollback.py --restore --run-id LAST_RUN_ID --scope run
```

---

## deploy.sh — Automated Setup

See `deploy.sh` in the repository root for automated setup.

---

## Status

- [ ] `deploy.sh` — created (stub, needs testing)
- [ ] Credentials setup — documented in MASTER_SETUP_GUIDE.md
- [ ] Scheduled runs — see MAINTENANCE_SCHEDULE.md
- [ ] Monitoring — see MONITORING_AND_ALERTING.md
