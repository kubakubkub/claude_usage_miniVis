"""Temporary probe: dump the raw statusLine payload so we can confirm field names.

Reads the JSON object Claude Code sends on stdin, appends it verbatim to
probe-dump.jsonl, and prints a minimal statusline so the UI still works.
Never raises; never prints a traceback to stdout.
"""
import json
import os
import sys
import time

DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe-dump.jsonl")


def main() -> None:
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        pass

    try:
        with open(DUMP, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"captured_at": time.time(), "raw": raw}) + "\n")
    except Exception:
        pass

    # Minimal, always-safe statusline.
    line = "probe"
    try:
        data = json.loads(raw)
        model = (data.get("model") or {}).get("display_name") or "?"
        line = "probe | %s" % model
    except Exception:
        pass
    sys.stdout.write(line)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stdout.write("probe")
