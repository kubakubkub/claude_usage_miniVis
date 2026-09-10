#!/usr/bin/env bash
# What past runs cost, and whether one still fits in what's left of your limits.
# Local only: reads files on disk, no network, no tokens.
cd "$(dirname "$0")" || exit 1
./claude-usage.sh report
