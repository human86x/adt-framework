#!/bin/bash
# ADT Enforcement Hook for Claude Code (ADT Framework Project)
# The framework governs itself by its own principles.
#
# Per ADT Framework (Sheridan, 2026):
# "Execution not authorised by an active specification is considered structurally invalid"

set -e

CORTEX_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/_cortex"
ADS_FILE="$CORTEX_DIR/ads/events.jsonl"

# Get tool info from environment (Claude Code passes these)
TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
FILE_PATH="${CLAUDE_FILE_PATH:-}"
CURRENT_ROLE="${CLAUDE_ROLE:-UNASSIGNED}"

# Helper: Log violation to ADS
log_violation() {
    local type="$1"
    local reason="$2"
    local ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local id="evt_$(date +%Y%m%d_%H%M%S)_$(printf '%03d' $RANDOM)"

    echo "{\"id\":\"$id\",\"ts\":\"$ts\",\"agent\":\"CLAUDE\",\"role\":\"$CURRENT_ROLE\",\"action_type\":\"$type\",\"spec_ref\":null,\"authority\":\"NONE\",\"authorized\":false,\"rationale\":\"$reason\",\"action_data\":{\"file\":\"$FILE_PATH\"},\"outcome\":\"blocked\",\"escalation\":true}" >> "$ADS_FILE"
}

# Helper: Check if file is in role jurisdiction (ADT Framework roles)
check_jurisdiction() {
    local file="$1"
    local role="$2"

    case "$role" in
        "Systems_Architect")
            [[ "$file" == *"_cortex/"* || "$file" == *"docs/"* ]] && return 0
            ;;
        "Backend_Engineer")
            [[ "$file" == *"adt_core/"* || "$file" == *"adt_center/app.py"* || "$file" == *"adt_center/api/"* || "$file" == *"adt_sdk/"* ]] && return 0
            ;;
        "Frontend_Engineer")
            [[ "$file" == *"adt_center/templates/"* || "$file" == *"adt_center/static/"* ]] && return 0
            ;;
        "DevOps_Engineer")
            [[ "$file" == *"config/"* || "$file" == *"setup.py"* || "$file" == *"tests/"* || "$file" == *".github/"* ]] && return 0
            ;;
        "Overseer")
            [[ "$file" == *"_cortex/ads/"* || "$file" == *"_cortex/reports/"* ]] && return 0
            ;;
    esac
    return 1
}

# Main enforcement logic
main() {
    # Only enforce on file-modifying tools
    case "$TOOL_NAME" in
        "Edit"|"Write"|"NotebookEdit")
            ;;
        *)
            exit 0  # Allow non-file tools
            ;;
    esac

    # Skip if no file path
    [[ -z "$FILE_PATH" ]] && exit 0

    # Skip ADS file itself (always allow logging)
    [[ "$FILE_PATH" == *"events.jsonl"* ]] && exit 0

    # Check 1: Role must be assigned
    if [[ "$CURRENT_ROLE" == "UNASSIGNED" ]]; then
        log_violation "unauthorized_attempt" "No role assigned. Use /hive-<role> first."
        echo "BLOCKED: No role assigned. Activate with /hive-<role> command first."
        exit 1
    fi

    # Check 2: Jurisdiction
    if ! check_jurisdiction "$FILE_PATH" "$CURRENT_ROLE"; then
        log_violation "jurisdiction_violation" "File outside jurisdiction for role $CURRENT_ROLE"
        echo "BLOCKED: $FILE_PATH is outside jurisdiction for $CURRENT_ROLE"
        exit 1
    fi

    # All checks passed
    exit 0
}

main "$@"
