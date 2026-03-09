#!/usr/bin/env bash
# StorageRationalizer — Cron Job Manager (STUB)
# See: docs/MAINTENANCE_SCHEDULE.md
# Status: STUB — review cron entries before installing

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$REPO_DIR/.venv/bin/python3"
LOG_DIR="$REPO_DIR/logs"
CRON_TAG="# StorageRationalizer"

# ── Cron entries ───────────────────────────────────────────────────────────
# Adjust times to suit your schedule before running --install

WEEKLY_SECURITY="0 9 * * 0 cd $REPO_DIR && $PYTHON -m pytest tests/security/ -q >> $LOG_DIR/cron_weekly.log 2>&1 $CRON_TAG"
MONTHLY_AUDIT="0 8 1 * * cd $REPO_DIR && pip list --outdated >> $LOG_DIR/cron_monthly.log 2>&1 $CRON_TAG"
MONTHLY_SNAPSHOT="30 8 1 * * cd $REPO_DIR && $PYTHON tools/financial_tracker.py --savings >> $LOG_DIR/cron_monthly.log 2>&1 $CRON_TAG"
LOG_ROTATION="0 0 1 * * find $LOG_DIR -name '*.log' -mtime +30 -delete $CRON_TAG"

install_crons() {
    echo "Installing StorageRationalizer cron jobs..."
    (crontab -l 2>/dev/null | grep -v "$CRON_TAG"; \
     echo "$WEEKLY_SECURITY"; \
     echo "$MONTHLY_AUDIT"; \
     echo "$MONTHLY_SNAPSHOT"; \
     echo "$LOG_ROTATION") | crontab -
    echo "Done. Current crontab:"
    crontab -l | grep "$CRON_TAG"
}

uninstall_crons() {
    echo "Removing StorageRationalizer cron jobs..."
    (crontab -l 2>/dev/null | grep -v "$CRON_TAG") | crontab -
    echo "Done."
}

list_crons() {
    echo "StorageRationalizer cron jobs:"
    crontab -l 2>/dev/null | grep "$CRON_TAG" || echo "  (none installed)"
}

case "${1:-}" in
    --install)   install_crons ;;
    --uninstall) uninstall_crons ;;
    --list)      list_crons ;;
    *)
        echo "Usage: $0 --install | --uninstall | --list"
        echo ""
        echo "WARNING: Review cron entries in this script before running --install."
        echo "See: docs/MAINTENANCE_SCHEDULE.md"
        exit 1
        ;;
esac
