#!/bin/bash
# Manual trigger: run the weekly email pipeline immediately.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
echo "Running weekly email pipeline..."
uv run python -m src.weekly_email
echo "Done."
