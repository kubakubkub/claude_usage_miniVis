"""Claude Code statusLine: print a one-line status AND mirror the payload to disk.

Claude Code pipes a JSON object to this script on stdin for every status line
render. We write the whole payload (plus a capture timestamp) to
%USERPROFILE%\\.claude\\usage-mirror.json so tray.pyw can display it, then print
a short human-readable line to stdout.

Hard rules:
  - Never raise. Never print a traceback to stdout. A broken statusline would
    show up as garbage in the Claude Code UI on every render.
  - No network calls, no API key, no credentials. Input is stdin only.
  - The mirror write is atomic (temp file + os.replace) so the tray never reads
    a half-written file.

rate_limits is absent under API-key auth, and absent right after /clear until
the session's first API response. Both cases degrade to "5h --".
"""
import json
import os
import sys
import tempfile
import time

MIRROR_NAME = "usage-mirror.json"


def mirror_path() -> str:
    base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(base, ".claude", MIRROR_NAME)


def trim(payload):
    """Keep only what the visualizers actually display.

    The full statusLine payload also carries session_id, transcript_path, cwd
    and cost.total_cost_usd. None of that is needed to draw a percentage, and
    the mirror is exactly the file someone would attach to a bug report -- so
    storing it would publish their project paths and spend. Pass --full to
    capture everything instead (or use probe_statusline.py, which is built for
    inspecting the schema).
    """
    if not isinstance(payload, dict):
        return None

    out = {}
    limits = payload.get("rate_limits")
    if isinstance(limits, dict):
        out["rate_limits"] = {k: v for k, v in limits.items()
                              if k in ("five_hour", "seven_day")}

    model = payload.get("model")
    if isinstance(model, dict) and model.get("display_name"):
        out["model"] = {"display_name": model["display_name"]}

    ctx = payload.get("context_window")
    if isinstance(ctx, dict):
        out["context_window"] = {k: ctx[k] for k in
                                 ("used_percentage", "remaining_percentage") if k in ctx}

    # Harmless and useful when a Claude Code upgrade changes the shape.
    if payload.get("version"):
        out["version"] = payload["version"]
    return out


def write_mirror(payload, raw: str, full: bool = False) -> None:
    """Atomically write the payload + capture time. Silent on any failure."""
    path = mirror_path()
    stored = payload if full else trim(payload)
    record = {
        "captured_at": time.time(),
        "payload": stored if isinstance(stored, dict) else None,
        "raw_ok": payload is not None,
        "trimmed": not full,
    }
    if payload is None and full:
        # Keep the unparseable text around; useful if the schema ever changes.
        record["raw"] = raw[:8000]

    tmp = None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".usage-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        os.replace(tmp, path)
        tmp = None
    except Exception:
        pass
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass


def dig(data, *keys):
    """Nested lookup that returns None instead of raising on any missing link."""
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def as_pct(value):
    """Coerce to int percent, or None if it isn't a usable number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return int(round(value))
    except Exception:
        return None


def build_line(data) -> str:
    if not isinstance(data, dict):
        return "claude"

    parts = []

    model = dig(data, "model", "display_name")
    parts.append(model if isinstance(model, str) and model else "claude")

    ctx = as_pct(dig(data, "context_window", "used_percentage"))
    parts.append("ctx %d%%" % ctx if ctx is not None else "ctx --")

    five = as_pct(dig(data, "rate_limits", "five_hour", "used_percentage"))
    parts.append("5h %d%%" % five if five is not None else "5h --")

    return " | ".join(parts)


def main() -> None:
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        pass

    data = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            data = parsed
    except Exception:
        pass

    write_mirror(data, raw, full="--full" in sys.argv[1:])
    sys.stdout.write(build_line(data))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Absolute last resort: emit something harmless, never a traceback.
        try:
            sys.stdout.write("claude")
        except Exception:
            pass
