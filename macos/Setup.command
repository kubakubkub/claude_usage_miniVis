#!/usr/bin/env bash
# Double-click me first: creates the venv in the repo root and installs deps.
#
# Finder cannot run a bare .sh, which is why these thin .command wrappers exist:
# they give macOS the same double-click-and-it-runs experience the .bat files
# give Windows. Each one just calls claude-usage.sh sitting next to it.
cd "$(dirname "$0")" || exit 1
./claude-usage.sh setup
