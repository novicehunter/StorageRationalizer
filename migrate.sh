#!/bin/bash
# StorageRationalizer Migration Script
# 1. Archives old Desktop folder
# 2. Replaces with clean V2
# 3. Archives old GitHub history and force-pushes clean V2
#
# Usage: bash migrate.sh
# Run from: ~/Desktop/StorageRationalizerV2/ (after unzipping)

set -e

DESKTOP=~/Desktop
OLD_DIR="$DESKTOP/StorageRationalizer"
NEW_DIR="$DESKTOP/StorageRationalizerV2"
ARCHIVE_DIR="$DESKTOP/StorageRationalizer_Archive"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
GITHUB_REPO="https://github.com/novicehunter/StorageRationalizer.git"

echo ""
echo "========================================"
echo "  StorageRationalizer Migration Script  "
echo "========================================"
echo ""

# ── Step 1: Archive old Desktop folder ──────────────────────────────────────
echo "▶ Step 1: Archiving old folder..."

if [ -d "$OLD_DIR" ]; then
    ARCHIVE_PATH="$ARCHIVE_DIR/StorageRationalizer_pre_v2_$TIMESTAMP.zip"
    mkdir -p "$ARCHIVE_DIR"
    zip -r "$ARCHIVE_PATH" "$OLD_DIR" -x "*.pyc" -x "*/__pycache__/*" -x "*/manifests/*.db*" -x "*/logs/*"
    echo "  ✅ Archived to: $ARCHIVE_PATH"

    # Copy manifests before deleting (they're valuable scan data)
    if [ -d "$OLD_DIR/manifests" ]; then
        mkdir -p "$NEW_DIR/manifests"
        cp "$OLD_DIR/manifests/"*.db "$NEW_DIR/manifests/" 2>/dev/null || true
        echo "  ✅ Copied manifest DBs to new folder"
    fi

    # Copy credentials before deleting
    if [ -d "$OLD_DIR/credentials" ]; then
        mkdir -p "$NEW_DIR/credentials"
        cp "$OLD_DIR/credentials/"* "$NEW_DIR/credentials/" 2>/dev/null || true
        echo "  ✅ Copied credentials to new folder"
    fi

    rm -rf "$OLD_DIR"
    echo "  ✅ Removed old folder"
else
    echo "  ℹ️  No old folder found at $OLD_DIR — skipping archive"
fi

# ── Step 2: Rename V2 to canonical name ─────────────────────────────────────
echo ""
echo "▶ Step 2: Installing clean V2 as StorageRationalizer..."

if [ "$NEW_DIR" != "$OLD_DIR" ]; then
    mv "$NEW_DIR" "$OLD_DIR"
    echo "  ✅ Renamed StorageRationalizerV2 → StorageRationalizer"
fi

cd "$OLD_DIR"

# ── Step 3: Archive GitHub history and push clean V2 ────────────────────────
echo ""
echo "▶ Step 3: Pushing clean V2 to GitHub..."

# Check if git is initialized
if [ ! -d ".git" ]; then
    git init
    git remote add origin "$GITHUB_REPO"
    echo "  ✅ Initialized git repo"
else
    # Ensure remote is set correctly
    git remote set-url origin "$GITHUB_REPO" 2>/dev/null || git remote add origin "$GITHUB_REPO"
    echo "  ✅ Git remote confirmed: $GITHUB_REPO"
fi

# Stage everything
git add .
git status

echo ""
read -p "  ❓ Ready to commit and force-push clean V2 to GitHub? (y/n): " CONFIRM
if [[ "$CONFIRM" != "y" ]]; then
    echo "  ⏸  Skipped GitHub push. Run manually when ready:"
    echo "     cd ~/Desktop/StorageRationalizer"
    echo "     git add . && git commit -m 'v2: clean consolidated repo'"
    echo "     git push --force origin main"
    exit 0
fi

git commit -m "v2: clean consolidated repo — scanner, classifier, verifier, cleaner, tracker, gphotos_test"
git push --force origin main

echo ""
echo "  ✅ Force-pushed clean V2 to GitHub"
echo "     Old history archived locally at: $ARCHIVE_DIR"
echo ""

# ── Done ────────────────────────────────────────────────────────────────────
echo "========================================"
echo "  ✅ Migration complete!"
echo ""
echo "  Desktop: ~/Desktop/StorageRationalizer (clean V2)"
echo "  GitHub:  https://github.com/novicehunter/StorageRationalizer"
echo "  Archive: $ARCHIVE_DIR/"
echo ""
echo "  Next: python3 phase3/cleaner.py --dry-run --mode all"
echo "========================================"
