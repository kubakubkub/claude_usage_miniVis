#!/usr/bin/env bash
# Wires statusline.py into Claude Code's settings.json. Backs up first.
# Run Setup.command once before this.
cd "$(dirname "$0")" || exit 1
./claude-usage.sh install
