#!/bin/bash
# Manual trigger: run the weekly email pipeline in TEST mode.
# Sends only to test_recipient and does NOT mark opportunities as emailed.
# Use --prod to send to all recipients (same as scheduled Thursday 8 PM run).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

if [ "${1:-}" = "--prod" ]; then
    echo "Running weekly email pipeline (PRODUCTION - all recipients)..."
    uv run python -m src.weekly_email
else
    echo "Running weekly email pipeline (TEST - test_recipient only)..."
    uv run python -m src.weekly_email --test
fi

echo "Done."
