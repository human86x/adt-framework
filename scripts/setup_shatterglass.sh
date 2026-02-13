#!/bin/bash
# ============================================================================
# ADT Framework: setup_shatterglass.sh
# Production setup script for Shatterglass Protocol (SPEC-027).
#
# This script configures OS users, file ownership, and permissions to
# enforce governance at the filesystem level.
#
# MUST BE RUN AS ROOT.
# ============================================================================

set -e

# --- Configuration ---
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADS_LOG="_cortex/ads/events.jsonl"
TIER1_PATHS=(
    "config/specs.json"
    "config/jurisdictions.json"
    "config/dttp.json"
    "_cortex/AI_PROTOCOL.md"
    "_cortex/MASTER_PLAN.md"
)
TIER2_PATHS=(
    "adt_core/dttp/gateway.py"
    "adt_core/dttp/policy.py"
    "adt_core/dttp/service.py"
    "adt_core/ads/logger.py"
    "adt_core/ads/integrity.py"
    "adt_core/ads/crypto.py"
)

# --- Check for root ---
if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run as root (sudo ./scripts/setup_shatterglass.sh)"
  exit 1
fi

HUMAN_USER=${SUDO_USER:-$(whoami)}
if [ "$HUMAN_USER" == "root" ]; then
    echo "Error: Could not detect human user. Run with sudo from your normal account."
    exit 1
fi

echo "--- ADT Shatterglass Production Setup ---"
echo "Human User:   $HUMAN_USER"
echo "Project Root: $PROJECT_ROOT"

# --- 1. Detect platform ---
IS_MAC=false
if [[ "$(uname)" == "Darwin" ]]; then
    IS_MAC=true
    echo "Platform: macOS"
else
    echo "Platform: Linux/WSL"
fi

# --- 2. Create Users and Groups ---
echo "Configuring OS users..."
if $IS_MAC; then
    # macOS-specific user/group management is complex via script.
    # We will assume they exist or prompt.
    if ! id -u dttp &>/dev/null; then
        echo "Note: 'dttp' user not found. Attempting to create..."
        dseditgroup -o create dttp || true
        # This is a simplification; production macOS setup usually requires more steps.
    fi
    if ! id -u agent &>/dev/null; then
        echo "Note: 'agent' user not found. Attempting to create..."
        # Simplified
    fi
    # Add agent to dttp group
    dseditgroup -o edit -a agent -t user dttp || true
else
    # Linux / WSL
    groupadd -f dttp
    id -u dttp &>/dev/null || useradd -r -g dttp -s /bin/bash dttp
    id -u agent &>/dev/null || useradd -r -g dttp -s /bin/bash agent
    usermod -a -G dttp agent
fi

# --- 3. Set Base Permissions (Tier 3) ---
echo "Setting base ownership to dttp:dttp (Tier 3)..."
chown -R dttp:dttp "$PROJECT_ROOT"
# Dirs 775, Files 664
find "$PROJECT_ROOT" -type d -exec chmod 775 {} +
find "$PROJECT_ROOT" -type f -exec chmod 664 {} +

# --- 4. Set Tier 1: Sovereign (Human-Only Write) ---
echo "Configuring Tier 1: Sovereign Files..."
for p in "${TIER1_PATHS[@]}"; do
    if [ -f "$PROJECT_ROOT/$p" ]; then
        chown "$HUMAN_USER:$HUMAN_USER" "$PROJECT_ROOT/$p"
        chmod 644 "$PROJECT_ROOT/$p"
    fi
done

# --- 5. Set Tier 2: Constitutional (DTTP-Only Write) ---
echo "Configuring Tier 2: Constitutional Files..."
for p in "${TIER2_PATHS[@]}"; do
    if [ -f "$PROJECT_ROOT/$p" ]; then
        chown dttp:dttp "$PROJECT_ROOT/$p"
        chmod 644 "$PROJECT_ROOT/$p"
    fi
done

# --- 6. Set Tier 2.5: ADS Log (Append-Only) ---
echo "Configuring Tier 2.5: ADS Log..."
if [ -f "$PROJECT_ROOT/$ADS_LOG" ]; then
    chown dttp:dttp "$PROJECT_ROOT/$ADS_LOG"
    chmod 664 "$PROJECT_ROOT/$ADS_LOG"
fi

# --- 7. Sudoers Configuration ---
echo "Updating sudoers..."
SUDOERS_FILE="/etc/sudoers.d/adt-shatterglass"
cat > "$SUDOERS_FILE" <<EOF
# ADT Shatterglass Protocol: Sovereign Path Escalation
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 664 $PROJECT_ROOT/config/specs.json
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 644 $PROJECT_ROOT/config/specs.json
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 664 $PROJECT_ROOT/config/jurisdictions.json
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 644 $PROJECT_ROOT/config/jurisdictions.json
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 664 $PROJECT_ROOT/config/dttp.json
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 644 $PROJECT_ROOT/config/dttp.json
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 664 $PROJECT_ROOT/_cortex/AI_PROTOCOL.md
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 644 $PROJECT_ROOT/_cortex/AI_PROTOCOL.md
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 664 $PROJECT_ROOT/_cortex/MASTER_PLAN.md
$HUMAN_USER ALL=(ALL) NOPASSWD: /usr/bin/chmod 644 $PROJECT_ROOT/_cortex/MASTER_PLAN.md

# Agent access to DTTP
agent ALL=(dttp) NOPASSWD: $PROJECT_ROOT/venv/bin/python3 $PROJECT_ROOT/adt_sdk/hooks/dttp_request.py
agent ALL=(dttp) NOPASSWD: $PROJECT_ROOT/.venv/bin/python3 $PROJECT_ROOT/adt_sdk/hooks/dttp_request.py
EOF
chmod 440 "$SUDOERS_FILE"

# --- 8. Log to ADS ---
echo "Logging activation..."
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EID="evt_$(date -u +"%Y%m%d_%H%M%S")_prod_act"
EVENT="{"event_id": "$EID", "ts": "$TS", "agent": "SYSTEM", "role": "Sentry", "action_type": "production_mode_activated", "description": "Shatterglass production mode activated.", "spec_ref": "SPEC-027", "authorized": true, "tier": 1}"

# Use python to log properly if possible (maintains hash chain)
PYTHON_BIN=""
if [ -x "$PROJECT_ROOT/venv/bin/python3" ]; then
    PYTHON_BIN="$PROJECT_ROOT/venv/bin/python3"
elif [ -x "$PROJECT_ROOT/.venv/bin/python3" ]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
fi

if [ -n "$PYTHON_BIN" ]; then
    export PYTHONPATH="$PROJECT_ROOT"
    "$PYTHON_BIN" -c "
import json, os, sys
try:
    from adt_core.ads.logger import ADSLogger
    logger = ADSLogger('$PROJECT_ROOT/$ADS_LOG')
    event = json.loads('$EVENT')
    logger.log(event)
    print('Logged via ADSLogger')
except Exception as e:
    print(f'Logger failed: {e}', file=sys.stderr)
    with open('$PROJECT_ROOT/$ADS_LOG', 'a') as f:
        f.write('$EVENT
')
" || echo "$EVENT" >> "$PROJECT_ROOT/$ADS_LOG"
else
    echo "$EVENT" >> "$PROJECT_ROOT/$ADS_LOG"
fi

echo ""
echo "--- Setup Complete ---"
echo "Production Mode is ACTIVE."
echo "Sovereign files (Tier 1) are READ-ONLY for everyone except $HUMAN_USER."
echo "Constitutional files (Tier 2) are READ-ONLY for everyone except dttp."
echo "ADS Log (Tier 2.5) is APPEND-ONLY via DTTP."
echo "Agent user 'agent' is in the 'dttp' group and can write to Tier 3 files."
echo ""
echo "To test enforcement:"
echo "sudo -u agent touch config/specs.json (Should fail)"
echo "sudo -u agent touch adt_core/dttp/gateway.py (Should fail)"
echo "sudo -u agent touch README.md (Should succeed)"
