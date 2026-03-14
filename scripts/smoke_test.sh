#!/usr/bin/env bash
# Morphic-Agent — Automated Smoke Test
# Usage: ./scripts/smoke_test.sh [API_BASE]
# Requires: curl, python3, running API server
set -euo pipefail

API="${1:-http://localhost:8000}"
PASS=0
FAIL=0
ERRORS=()

# ── Helpers ──────────────────────────────────────────────────────
green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

check() {
  local name="$1" status="$2" body="$3"
  if [ "$status" -ge 200 ] && [ "$status" -lt 300 ]; then
    green "  ✓ $name (HTTP $status)"
    PASS=$((PASS + 1))
  else
    red "  ✗ $name (HTTP $status)"
    ERRORS+=("$name: HTTP $status — $body")
    FAIL=$((FAIL + 1))
  fi
}

api() {
  local method="$1" path="$2" data="${3:-}"
  if [ -n "$data" ]; then
    curl -s -w "\n%{http_code}" -X "$method" "$API$path" \
      -H "Content-Type: application/json" -d "$data"
  else
    curl -s -w "\n%{http_code}" -X "$method" "$API$path"
  fi
}

extract() {
  # Split response body and status code
  local response="$1"
  BODY=$(echo "$response" | sed '$d')
  STATUS=$(echo "$response" | tail -1)
}

# ── Phase 0: Infrastructure ─────────────────────────────────────
bold "Phase 0: Infrastructure"

extract "$(api GET /api/health)"
check "Health endpoint" "$STATUS" "$BODY"

# ── Phase 1: Task CRUD ───────────────────────────────────────────
bold "Phase 1: Task CRUD"

extract "$(api GET /api/tasks)"
check "List tasks" "$STATUS" "$BODY"
TASK_COUNT=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "?")
echo "    Tasks in DB: $TASK_COUNT"

# ── Phase 2: Models ──────────────────────────────────────────────
bold "Phase 2: Model Management"

extract "$(api GET /api/models/status)"
check "Model status" "$STATUS" "$BODY"
OLLAMA_UP=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['ollama_running'])" 2>/dev/null || echo "?")
DEFAULT_MODEL=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['default_model'])" 2>/dev/null || echo "?")
echo "    Ollama: $OLLAMA_UP | Default: $DEFAULT_MODEL"

extract "$(api GET /api/models)"
check "List models" "$STATUS" "$BODY"
MODEL_COUNT=$(echo "$BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['models']))" 2>/dev/null || echo "?")
echo "    Available models: $MODEL_COUNT"

extract "$(api GET /api/models/running)"
check "Running models" "$STATUS" "$BODY"

# ── Phase 3: Cost Tracking ───────────────────────────────────────
bold "Phase 3: Cost Tracking"

extract "$(api GET /api/cost)"
check "Cost summary" "$STATUS" "$BODY"
DAILY=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'\${d[\"daily_total_usd\"]:.4f}')" 2>/dev/null || echo "?")
MONTHLY=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'\${d[\"monthly_total_usd\"]:.4f}')" 2>/dev/null || echo "?")
echo "    Daily: $DAILY | Monthly: $MONTHLY"

extract "$(api GET '/api/cost/logs?limit=5')"
check "Cost logs" "$STATUS" "$BODY"

# ── Phase 4: Engines ─────────────────────────────────────────────
bold "Phase 4: Agent Engines"

extract "$(api GET /api/engines)"
check "List engines" "$STATUS" "$BODY"
ENGINE_COUNT=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "?")
echo "    Engines: $ENGINE_COUNT"

extract "$(api GET /api/engines/ollama)"
check "Ollama engine status" "$STATUS" "$BODY"

# ── Phase 5: Marketplace ─────────────────────────────────────────
bold "Phase 5: Marketplace"

extract "$(api GET '/api/marketplace/search?q=github&limit=3')"
check "Search tools" "$STATUS" "$BODY"

extract "$(api GET /api/marketplace/installed)"
check "Installed tools" "$STATUS" "$BODY"

extract "$(api POST /api/marketplace/suggest '{"error_message":"FileNotFoundError","task_description":"file processing"}')"
check "Tool suggestions" "$STATUS" "$BODY"

# ── Phase 6: Evolution ───────────────────────────────────────────
bold "Phase 6: Evolution"

extract "$(api GET /api/evolution/stats)"
check "Execution stats" "$STATUS" "$BODY"

extract "$(api GET '/api/evolution/failures?limit=5')"
check "Failure patterns" "$STATUS" "$BODY"

extract "$(api GET /api/evolution/preferences)"
check "Learned preferences" "$STATUS" "$BODY"

# ── Phase 7: UCL (Cognitive) ─────────────────────────────────────
bold "Phase 7: Unified Cognitive Layer"

extract "$(api GET /api/cognitive/state)"
check "Shared task states" "$STATUS" "$BODY"

extract "$(api GET /api/cognitive/affinity)"
check "Affinity scores" "$STATUS" "$BODY"

extract "$(api POST /api/cognitive/insights/extract '{"task_id":"smoke-001","engine":"ollama","output":"Test insight"}')"
check "Extract insights" "$STATUS" "$BODY"

# ── Phase 8: Benchmarks ──────────────────────────────────────────
bold "Phase 8: Benchmarks"

extract "$(api POST /api/benchmarks/continuity)"
check "Continuity benchmark" "$STATUS" "$BODY"

extract "$(api POST /api/benchmarks/dedup)"
check "Dedup benchmark" "$STATUS" "$BODY"

# ── Phase 9: Error Handling ──────────────────────────────────────
bold "Phase 9: Error Handling"

extract "$(api GET /api/tasks/nonexistent-id-12345)"
if [ "$STATUS" -eq 404 ]; then
  green "  ✓ 404 on missing task (HTTP $STATUS)"
  PASS=$((PASS + 1))
else
  red "  ✗ Expected 404 on missing task (HTTP $STATUS)"
  FAIL=$((FAIL + 1))
fi

# ── Summary ──────────────────────────────────────────────────────
echo ""
bold "═══════════════════════════════════════"
bold " Smoke Test Results: $PASS passed, $FAIL failed"
bold "═══════════════════════════════════════"

if [ ${#ERRORS[@]} -gt 0 ]; then
  echo ""
  red "Failures:"
  for e in "${ERRORS[@]}"; do
    red "  - $e"
  done
fi

exit $FAIL
