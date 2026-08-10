#!/usr/bin/env bash
# Stops the overlay, the tray and the chooser. The statusLine is untouched --
# remove that with:  ./claude-usage.sh uninstall
cd "$(dirname "$0")" || exit 1
./claude-usage.sh stop
