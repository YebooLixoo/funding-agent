#!/bin/bash
# Manual trigger: run the weekly fetch pipeline immediately.
# Fetches opportunities from the last 7 days (or since last successful fetch).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
echo "Running weekly fetch pipeline..."
uv run python -m src.weekly_fetch
echo "Done."
