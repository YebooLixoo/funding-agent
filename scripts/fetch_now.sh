#!/bin/bash
# Manual trigger: run the daily fetch pipeline immediately.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
echo "Running daily fetch pipeline..."
uv run python -m src.daily_fetch
echo "Done."
