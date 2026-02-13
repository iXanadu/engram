#!/bin/bash
# Restart engram service
#
# Usage:
#   ./scripts/restart.sh

set -e

LABEL="com.engram"

if [[ "$(uname)" == "Darwin" ]]; then
    if ! sudo launchctl list "$LABEL" &>/dev/null; then
        echo "Service not running. Use ./scripts/start.sh to start."
        exit 1
    fi

    sudo launchctl kickstart -k "system/${LABEL}"
    echo "Service restarted"

elif [[ "$(uname)" == "Linux" ]]; then
    sudo systemctl restart engram
    echo "Service restarted"
fi

# Wait briefly and verify
sleep 2
if curl -sf http://localhost:8920/health > /dev/null 2>&1; then
    echo "Health check: OK"
else
    echo "WARNING: Health check failed — check logs"
    if [[ "$(uname)" == "Darwin" ]]; then
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        APP_DIR="$(dirname "$SCRIPT_DIR")"
        echo "  tail -f $APP_DIR/logs/engram.err"
    else
        echo "  journalctl -u engram -f"
    fi
fi
