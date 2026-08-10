#!/usr/bin/env bash
# macOS / Linux launcher for claude_usage_miniVis.
#
#   ./claude-usage.sh setup      create venv + install deps
#   ./claude-usage.sh install    wire statusline.py into settings.json (backs up)
#   ./claude-usage.sh uninstall  remove the statusLine key
#   ./claude-usage.sh choose     preview the three presets and start one
#   ./claude-usage.sh overlay    start the always-on-top desktop badge
#   ./claude-usage.sh tray       start the menu-bar / tray icon
#   ./claude-usage.sh stop       stop both
#   ./claude-usage.sh status     show what's running and the current numbers
#
# Reads only the local mirror file. No network calls, no credentials.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

need_venv() {
  if [ ! -x "$PY" ]; then
    echo "[ERROR] venv not found at $VENV"
    echo "        Run: ./claude-usage.sh setup"
    exit 1
  fi
}

# Match a running component by the script name in its command line.
#
# Case-INSENSITIVE (-i) on purpose. A Tk process on macOS does not keep the venv's
# lowercase "python" in its command line: Tkinter needs a windowed app bundle, so the
# interpreter re-execs itself through the framework stub and argv becomes
#   .../Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python overlay.pyw
# -- every "python" in that string is capitalised. A case-sensitive pattern therefore never
# matches on macOS, and the launcher reports "failed to stay running" for a process that
# started perfectly well, then leaves it orphaned (stop/status cannot see it either).
pids_for() { pgrep -if "python.*$1" 2>/dev/null || true; }

start_bg() {
  local script="$1" label="$2"
  need_venv
  if [ -n "$(pids_for "$script")" ]; then
    echo "$label is already running - nothing to do."
    return 0
  fi
  nohup "$PY" "$ROOT/$script" >/dev/null 2>&1 &
  sleep 2
  if [ -n "$(pids_for "$script")" ]; then
    echo "$label started."
  else
    echo "[ERROR] $label failed to stay running. Try in the foreground to see why:"
    echo "        $PY $ROOT/$script"
    return 1
  fi
}

stop_one() {
  local script="$1" label="$2"
  local pids
  pids="$(pids_for "$script")"
  if [ -z "$pids" ]; then
    echo "$label is not running."
    return 0
  fi
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  echo "$label stopped."
}

case "${1:-}" in
  setup)
    echo "Creating venv at $VENV"
    python3 -m venv "$VENV"
    "$PY" -m pip install --quiet --upgrade pip
    "$PY" -m pip install --quiet -r "$ROOT/requirements.txt"
    echo "Done. Next:  ./claude-usage.sh install"
    ;;
  install)   need_venv; "$PY" "$ROOT/install_statusline.py" ;;
  uninstall) need_venv; "$PY" "$ROOT/install_statusline.py" --uninstall ;;
  choose)    start_bg chooser.pyw "Chooser" ;;
  overlay)   start_bg overlay.pyw "Overlay" ;;
  tray)      start_bg tray.pyw "Tray" ;;
  stop)
    stop_one overlay.pyw "Overlay"
    stop_one tray.pyw "Tray"
    stop_one chooser.pyw "Chooser"
    ;;
  status)
    [ -n "$(pids_for overlay.pyw)" ] && echo "overlay: running" || echo "overlay: stopped"
    [ -n "$(pids_for tray.pyw)" ]    && echo "tray:    running" || echo "tray:    stopped"
    echo
    need_venv
    "$PY" -c "
import sys; sys.path.insert(0, '$ROOT')
import usage_core as core
s = core.read_state()
print(core.build_tooltip(s))
"
    ;;
  *)
    sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
