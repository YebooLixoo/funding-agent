#!/bin/bash
# Install LaunchAgents for funding-agent weekly fetch and email.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "Installing funding-agent LaunchAgents..."

# Ensure log directory exists
mkdir -p "$PROJECT_DIR/outputs/logs"

# Copy plist files
cp "$PROJECT_DIR/launchd/com.boyu.funding-agent.daily.plist" "$LAUNCH_AGENTS_DIR/"
cp "$PROJECT_DIR/launchd/com.boyu.funding-agent.weekly.plist" "$LAUNCH_AGENTS_DIR/"

# Load agents
launchctl load "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.daily.plist"
launchctl load "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.weekly.plist"

echo "Installed and loaded:"
echo "  - com.boyu.funding-agent.daily  (every Thursday at 12:00 PM MT - fetch)"
echo "  - com.boyu.funding-agent.weekly (every Thursday at  8:00 PM MT - email)"
echo ""
echo "Check status with:"
echo "  launchctl list | grep funding-agent"
