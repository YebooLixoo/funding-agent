#!/bin/bash
# Uninstall LaunchAgents for funding-agent.
set -euo pipefail

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "Uninstalling funding-agent LaunchAgents..."

# Unload agents (ignore errors if not loaded)
launchctl unload "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.fetch.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.email.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.backup.plist" 2>/dev/null || true

# Remove plist files
rm -f "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.fetch.plist"
rm -f "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.email.plist"
rm -f "$LAUNCH_AGENTS_DIR/com.boyu.funding-agent.backup.plist"

echo "Uninstalled funding-agent LaunchAgents."
