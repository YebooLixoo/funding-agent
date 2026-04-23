#!/bin/bash
# Install LaunchAgents for funding-agent fetch, email, and backup.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "Installing funding-agent LaunchAgents..."

# Ensure log directory exists
mkdir -p "$PROJECT_DIR/outputs/logs"

# Copy plist files (post-consolidation: fetch / email / backup)
cp "$PROJECT_DIR/launchd/com.boyu.funding-agent.fetch.plist" "$LAUNCH_AGENTS_DIR/"
cp "$PROJECT_DIR/launchd/com.boyu.funding-agent.email.plist" "$LAUNCH_AGENTS_DIR/"
cp "$PROJECT_DIR/launchd/com.boyu.funding-agent.backup.plist" "$LAUNCH_AGENTS_DIR/"

# Load agents
launchctl load "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.fetch.plist"
launchctl load "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.email.plist"
launchctl load "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.backup.plist"

echo "Installed and loaded:"
echo "  - com.boyu.funding-agent.fetch  (noon fetch pipeline)"
echo "  - com.boyu.funding-agent.email  (digest dispatch)"
echo "  - com.boyu.funding-agent.backup (DB backup)"
echo ""
echo "Check status with:"
echo "  launchctl list | grep funding-agent"
