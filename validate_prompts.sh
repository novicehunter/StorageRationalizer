#!/bin/bash

echo "=== Checking Prompt Completion ==="
echo ""

# Check 1: verify_cleanup.py exists
if [ -f "tools/verify_cleanup.py" ]; then
  echo "✅ Prompt 1: verify_cleanup.py exists"
else
  echo "❌ Prompt 1: verify_cleanup.py missing"
fi

# Check 2: tracker.py has /api/cleanup_status
if grep -q "/api/cleanup_status" tools/tracker.py; then
  echo "✅ Prompt 2: tracker.py updated with /api/cleanup_status"
else
  echo "❌ Prompt 2: /api/cleanup_status route not found"
fi

# Check 3: tracker.html has Cleanup Monitor tab
if grep -q "Cleanup Monitor" tools/tracker.html; then
  echo "✅ Prompt 3: tracker.html has Cleanup Monitor tab"
else
  echo "❌ Prompt 3: Cleanup Monitor tab not found"
fi

# Check 4: rollback.py exists
if [ -f "tools/rollback.py" ]; then
  echo "✅ Prompt 4: tools/rollback.py exists"
else
  echo "❌ Prompt 4: tools/rollback.py missing"
fi

# Check 5: CLAUDE.md updated with Phase 9.5 & 10
if grep -q "Phase 9.5" CLAUDE.md; then
  echo "✅ Prompt 5: CLAUDE.md updated with Phase 9.5"
else
  echo "❌ Prompt 5: Phase 9.5 not found in CLAUDE.md"
fi

echo ""
echo "=== Git Status ==="
git status
echo ""
echo "=== Recent Commits ==="
git log --oneline -5
