#!/usr/bin/env bash
# Shows what is running plus the current numbers -- the quickest check that the
# statusLine is feeding the mirror file.
cd "$(dirname "$0")" || exit 1
./claude-usage.sh status
