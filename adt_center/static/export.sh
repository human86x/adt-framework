#!/bin/bash
# ADT Panel Static Export & Deploy
# SPEC-015 Section 3.8: Mirror Export
#
# Usage:
#   ./export.sh              Export only (no upload)
#   ./export.sh --deploy     Export + FTP upload (prompts for password)
#   ./export.sh --auto       Export + FTP upload using saved credentials
#   ./export.sh --watch      Watch for changes and auto-deploy continuously
#
# Credentials for --auto/--watch: ~/.adt_ftp_credentials
#   Format: single line with the FTP password
#   Create with: echo 'yourpassword' > ~/.adt_ftp_credentials && chmod 600 ~/.adt_ftp_credentials

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
EXPORT_DIR="/tmp/adt-static-export"
FTP_HOST="ftp.oceanpulse.pt"
FTP_USER="oceanpul"
FTP_PATH="/www/adt-framework"
FLASK_URL="http://localhost:5001"
CRED_FILE="$HOME/.adt_ftp_credentials"

# Files to watch for changes
WATCH_FILES=(
    "$PROJECT_ROOT/_cortex/ads/events.jsonl"
    "$PROJECT_ROOT/_cortex/tasks.json"
    "$PROJECT_ROOT/_cortex/specs"
    "$PROJECT_ROOT/adt_center/templates"
    "$PROJECT_ROOT/adt_center/static/css/adt.css"
)

WATCH_INTERVAL=10  # seconds between checks in watch mode

do_export() {
    # Check Flask is running
    if ! curl -s -o /dev/null -w "" "$FLASK_URL/" 2>/dev/null; then
        echo "[$(date +%H:%M:%S)] ERROR: Flask not running on $FLASK_URL"
        return 1
    fi

    rm -rf "$EXPORT_DIR"
    mkdir -p "$EXPORT_DIR/css"

    # Export all pages
    curl -s "$FLASK_URL/"      -o "$EXPORT_DIR/index.html"
    curl -s "$FLASK_URL/ads"   -o "$EXPORT_DIR/ads.html"
    curl -s "$FLASK_URL/specs" -o "$EXPORT_DIR/specs.html"
    curl -s "$FLASK_URL/tasks" -o "$EXPORT_DIR/tasks.html"
    curl -s "$FLASK_URL/dttp"  -o "$EXPORT_DIR/dttp.html"
    curl -s "$FLASK_URL/about" -o "$EXPORT_DIR/about.html"

    # Copy CSS
    cp "$SCRIPT_DIR/css/adt.css" "$EXPORT_DIR/css/adt.css"

    # Fix paths for static hosting
    for f in "$EXPORT_DIR"/*.html; do
        sed -i 's|/static/css/adt.css|css/adt.css|g' "$f"
        sed -i 's|href="/ads"|href="ads.html"|g' "$f"
        sed -i 's|href="/specs"|href="specs.html"|g' "$f"
        sed -i 's|href="/tasks"|href="tasks.html"|g' "$f"
        sed -i 's|href="/dttp"|href="dttp.html"|g' "$f"
        sed -i 's|href="/about"|href="about.html"|g' "$f"
        sed -i 's|href="/"|href="index.html"|g' "$f"
    done

    echo "[$(date +%H:%M:%S)] Export complete"
}

do_deploy() {
    local pass="$1"
    for f in "$EXPORT_DIR"/*.html; do
        fname=$(basename "$f")
        curl -s -T "$f" -u "$FTP_USER:$pass" "ftp://$FTP_HOST$FTP_PATH/$fname"
    done
    curl -s -T "$EXPORT_DIR/css/adt.css" -u "$FTP_USER:$pass" "ftp://$FTP_HOST$FTP_PATH/css/adt.css"
    echo "[$(date +%H:%M:%S)] Deployed to https://oceanpulse.pt/adt-framework/"
}

get_fingerprint() {
    # Get a combined fingerprint of all watched files/dirs
    local fp=""
    for f in "${WATCH_FILES[@]}"; do
        if [ -f "$f" ]; then
            fp+="$(stat -c %Y "$f" 2>/dev/null)"
        elif [ -d "$f" ]; then
            fp+="$(find "$f" -type f -exec stat -c %Y {} + 2>/dev/null | sort | md5sum | cut -d' ' -f1)"
        fi
    done
    echo "$fp"
}

load_credentials() {
    if [ -f "$CRED_FILE" ]; then
        cat "$CRED_FILE"
    else
        echo ""
    fi
}

# --- Main ---

case "${1:-}" in
    --deploy)
        echo "=== ADT Panel Export + Deploy ==="
        do_export
        read -sp "FTP Password: " FTP_PASS
        echo ""
        do_deploy "$FTP_PASS"
        ;;

    --auto)
        echo "=== ADT Panel Auto Deploy ==="
        FTP_PASS=$(load_credentials)
        if [ -z "$FTP_PASS" ]; then
            echo "ERROR: No credentials found at $CRED_FILE"
            echo "Create with: echo 'password' > $CRED_FILE && chmod 600 $CRED_FILE"
            exit 1
        fi
        do_export
        do_deploy "$FTP_PASS"
        ;;

    --watch)
        echo "=== ADT Panel Watch Mode ==="
        echo "Watching for changes every ${WATCH_INTERVAL}s..."
        echo "Watched: events.jsonl, tasks.json, specs/, templates/, adt.css"
        echo "Press Ctrl+C to stop"
        echo ""

        FTP_PASS=$(load_credentials)
        if [ -z "$FTP_PASS" ]; then
            echo "ERROR: No credentials found at $CRED_FILE"
            echo "Create with: echo 'password' > $CRED_FILE && chmod 600 $CRED_FILE"
            exit 1
        fi

        # Initial deploy
        do_export && do_deploy "$FTP_PASS"
        LAST_FP=$(get_fingerprint)

        while true; do
            sleep "$WATCH_INTERVAL"
            CURRENT_FP=$(get_fingerprint)
            if [ "$CURRENT_FP" != "$LAST_FP" ]; then
                echo "[$(date +%H:%M:%S)] Change detected, redeploying..."
                if do_export; then
                    do_deploy "$FTP_PASS"
                fi
                LAST_FP=$(get_fingerprint)
            fi
        done
        ;;

    "")
        echo "=== ADT Panel Export (no deploy) ==="
        do_export
        ls -lh "$EXPORT_DIR"
        ;;

    *)
        echo "Usage: $0 [--deploy|--auto|--watch]"
        exit 1
        ;;
esac
