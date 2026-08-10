#!/usr/bin/env bash
# Starts the menu-bar icon. Safe to double-click twice -- the launcher refuses
# to start a second copy.
cd "$(dirname "$0")" || exit 1
./claude-usage.sh tray
