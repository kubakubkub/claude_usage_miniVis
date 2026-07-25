"""Wire statusline.py into Claude Code's settings.json -- no hand-editing, no jq.

  python install_statusline.py              install (backs up first)
  python install_statusline.py --uninstall  remove the statusLine key
  python install_statusline.py --show       print current setting and exit

Only ever touches the "statusLine" key. Everything else in settings.json is
preserved byte-for-byte in a timestamped backup before any write.

Never reads or writes ANTHROPIC_API_KEY, and never makes a network call.
"""
import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))


def settings_path() -> str:
    base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(base, ".claude", "settings.json")


def venv_python() -> str:
    """Prefer the project venv; fall back to whatever interpreter is running."""
    if os.name == "nt":
        cand = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    else:
        cand = os.path.join(ROOT, ".venv", "bin", "python")
    return cand if os.path.exists(cand) else sys.executable


def build_command() -> str:
    py = venv_python().replace("\\", "/")
    script = os.path.join(ROOT, "statusline.py").replace("\\", "/")
    # Quote so paths containing spaces survive the shell.
    return '"%s" "%s"' % (py, script)


def owns(current) -> bool:
    """Is the configured statusLine this project's own script?"""
    if not isinstance(current, dict):
        return False
    cmd = (current.get("command") or "").replace("\\", "/")
    return os.path.join(ROOT, "statusline.py").replace("\\", "/") in cmd


def load_settings(path):
    if not os.path.exists(path):
        return {}, False
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
        if not text:
            return {}, True
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("settings.json is not a JSON object")
        return data, True
    except Exception as exc:
        print("[ERROR] Could not parse %s\n        %s" % (path, exc))
        print("        Refusing to overwrite a file I can't read. Fix or move it first.")
        raise SystemExit(1)


def backup(path) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = "%s.bak-%s" % (path, stamp)
    shutil.copy2(path, dest)
    return dest


def write_settings(path, data) -> None:
    """Atomic write so a crash can't leave settings.json truncated."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description="Install the Claude usage statusLine.")
    ap.add_argument("--uninstall", action="store_true", help="remove the statusLine key")
    ap.add_argument("--show", action="store_true", help="print the current setting and exit")
    ap.add_argument("--force", action="store_true",
                    help="replace someone else's statusLine without asking")
    args = ap.parse_args()

    path = settings_path()
    data, existed = load_settings(path)
    current = data.get("statusLine")

    if args.show:
        print("settings: %s" % path)
        print("statusLine: %s" % (json.dumps(current, indent=2) if current else "<not set>"))
        return 0

    if args.uninstall:
        if not current:
            print("No statusLine set - nothing to remove.")
            return 0
        print("Backed up: %s" % backup(path))
        data.pop("statusLine", None)
        write_settings(path, data)
        print("Removed the statusLine key. Restart Claude Code to see the change.")
        return 0

    script = os.path.join(ROOT, "statusline.py")
    if not os.path.exists(script):
        print("[ERROR] statusline.py not found next to this installer: %s" % script)
        return 1

    command = build_command()

    # Check before backing up, so repeat runs don't litter the directory with
    # identical backups of a file nothing is about to change.
    if current and current.get("command") == command:
        print("Already installed and pointing at the right script. Nothing to do.")
        return 0

    # Plenty of people already run a statusLine. Silently replacing it is a
    # nasty surprise, backup or not -- so ask, unless it's one of ours.
    if current and not owns(current) and not args.force:
        print("A different statusLine is already configured:")
        print("  %s" % current.get("command"))
        print()
        print("Installing will replace it. A timestamped backup is written first,")
        print("and `--uninstall` restores nothing automatically -- keep that backup.")
        try:
            answer = input("Replace it? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("y", "yes"):
            print()
            print("Left unchanged. Re-run with --force to replace without asking.")
            return 1

    if existed:
        print("Backed up: %s" % backup(path))
    else:
        print("No settings.json yet - creating one.")

    if current:
        print("Replacing existing statusLine:")
        print("  old: %s" % current.get("command"))

    data["statusLine"] = {"type": "command", "command": command}
    write_settings(path, data)

    print("Installed statusLine ->")
    print("  %s" % command)
    print()
    print("Restart Claude Code (or start a new session) to pick it up.")
    print("The tray/overlay will show data after the first status line render.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print("[ERROR] %s" % exc)
        raise SystemExit(1)
