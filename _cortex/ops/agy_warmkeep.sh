#!/usr/bin/env bash
# agy_warmkeep.sh -- keep agy's OAuth token alive by touching an auth-sensitive
# command every 20 minutes. Prevents mid-build "auth expired" failures during
# demo takes and long forge runs.
#
# Usage:
#   nohup /home/human/Projects/adt-framework/_cortex/ops/agy_warmkeep.sh > /tmp/agy_warmkeep.log 2>&1 &
#   disown
#
# Stop:
#   pkill -f agy_warmkeep.sh
#
# Configurable via env:
#   ADT_AGY_WARM_INTERVAL_SEC  (default 1200 = 20 min)
#   ADT_AGY_WARM_LOG           (default /tmp/agy_warmkeep.log)

set -u

INTERVAL_SEC="${ADT_AGY_WARM_INTERVAL_SEC:-1200}"
LOG_FILE="${ADT_AGY_WARM_LOG:-/tmp/agy_warmkeep.log}"
AGY_BIN="$(command -v agy || echo /home/human/.local/bin/agy)"

if [ ! -x "$AGY_BIN" ]; then
  echo "$(date -Iseconds) agy binary not found or not executable: $AGY_BIN" >> "$LOG_FILE"
  exit 1
fi

echo "$(date -Iseconds) agy_warmkeep starting -- interval=${INTERVAL_SEC}s bin=$AGY_BIN pid=$$" >> "$LOG_FILE"

CONSECUTIVE_FAILURES=0
MAX_FAILURES=3

while true; do
  # Auth-touching probe; 15s hard cap so a hung agy can't block the loop
  if OUT=$(timeout 15 "$AGY_BIN" models 2>&1); then
    echo "$(date -Iseconds) OK -- probe succeeded" >> "$LOG_FILE"
    CONSECUTIVE_FAILURES=0
  else
    RC=$?
    CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
    # Echo the first 200 chars of failure output for context
    SHORT=$(printf '%s' "$OUT" | tr -d '\n' | cut -c1-200)
    echo "$(date -Iseconds) FAIL rc=$RC ($CONSECUTIVE_FAILURES/$MAX_FAILURES) -- $SHORT" >> "$LOG_FILE"

    # Emit an ADS event on repeated failure so the Console can surface it
    if [ "$CONSECUTIVE_FAILURES" -ge "$MAX_FAILURES" ]; then
      ADT_AGENT_LABEL=SYSTEM ADT_ROLE=DevOps_Engineer \
        python3 /home/human/Projects/adt-framework/_cortex/log_event.py \
          --type agy_auth_stale_detected \
          --spec REQ-124 \
          --description "agy warm-keep detected $MAX_FAILURES consecutive probe failures. OAuth likely expired. Operator action: run 'agy models' interactively and complete OAuth flow." \
          >> "$LOG_FILE" 2>&1 || true
      CONSECUTIVE_FAILURES=0  # reset so we don't spam every minute
    fi
  fi

  sleep "$INTERVAL_SEC"
done
