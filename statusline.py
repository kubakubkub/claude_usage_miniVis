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

Whenever a rate-limit window rises or resets, one line is also appended to
usage-history.jsonl. The mirror only ever holds the latest value;
the history is what shows how fast the percentages move. At most every 30
minutes this also starts usage_learn.py in the background, which learns from
that history; the status line never waits for it.
"""
import json
import os
import sys
import tempfile
import time

MIRROR_NAME = "usage-mirror.json"
HISTORY_NAME = "usage-history.jsonl"
HISTORY_ROLLED_NAME = "usage-history.1.jsonl"
# ~12k records. A line is only written when a percentage or reset time
# changes, so this is months of use; beyond it the file rolls over once.
HISTORY_MAX_BYTES = 1024 * 1024
# One window's resets_at can wobble by a second between renders.
RESET_TOLERANCE_SECONDS = 600
MODEL_NAME = "usage-model.json"  # written by usage_learn.py
LEARN_LOCK_NAME = "usage-learn.lock"
LEARN_EVERY_SECONDS = 30 * 60
# A learner that crashed leaves its lock behind; after this long it's ignored.
LEARN_LOCK_STALE_SECONDS = 10 * 60


def claude_path(name: str) -> str:
    base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(base, ".claude", name)


def mirror_path() -> str:
    return claude_path(MIRROR_NAME)


def history_path() -> str:
    return claude_path(HISTORY_NAME)


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


def as_num(value):
    """The number unchanged, or None if it isn't one. Unlike as_pct, keeps
    fractions: the history should record what Claude Code sent."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def has_limits(payload) -> bool:
    return any(as_num(dig(payload, "rate_limits", window, "used_percentage")) is not None
               for window in ("five_hour", "seven_day"))


def last_logged():
    """The history's last record, or None. Reads only the end of the file."""
    try:
        with open(history_path(), "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 4096))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except ValueError:
            continue  # the cut-off first line of the tail, or a torn write
        if isinstance(record, dict):
            return record
    return None


def append_history(payload, now: float) -> None:
    """Append the rate limits to the history when a window rose or started.
    Silent on failure.

    Every open Claude Code session renders its own status line from its own
    last API response, so an idle session keeps reporting an older, lower
    number. Usage can't go down inside a window, so a lower reading is stale:
    the record keeps the higher value, and nothing is written unless something
    actually moved. Readings for a window that has already reset are stale too.

    Timestamps and percentages only -- no session, path, model or cost data, for
    the same reason trim() exists. Two sessions rendering at the same instant
    can still log one change twice; readers tolerate that.
    """
    last = last_logged() or {}
    record = {"t": round(now, 1)}
    moved = False
    for window, short in (("five_hour", "5h"), ("seven_day", "7d")):
        pct = as_num(dig(payload, "rate_limits", window, "used_percentage"))
        reset = as_num(dig(payload, "rate_limits", window, "resets_at"))
        if pct is None or reset is None or reset <= now:
            continue
        # Payload percentages arrive as floats like 14.000000000000002. Round
        # before comparing, or the stored 14.0 reads as lower every render.
        pct = round(pct, 2)
        last_pct = as_num(last.get(short))
        last_reset = as_num(last.get(short + "_reset"))
        if (last_pct is not None and last_reset is not None
                and abs(reset - last_reset) <= RESET_TOLERANCE_SECONDS and pct <= last_pct):
            pct, reset = last_pct, last_reset
        else:
            moved = True
        record[short] = pct
        record[short + "_reset"] = reset
    if not moved:
        return

    path = history_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            if os.path.getsize(path) > HISTORY_MAX_BYTES:
                os.replace(path, claude_path(HISTORY_ROLLED_NAME))
        except OSError:
            pass  # No history yet, or the rollover lost a race with another session.
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except Exception:
        pass


def spawn_detached(args) -> None:
    """Start a process that outlives this one and shares no stdio with it -- an
    inherited stdout would keep Claude Code waiting on this status line."""
    import subprocess  # Needed about twice an hour; keep it out of every render.

    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL, close_fds=True)
    if os.name != "nt":
        subprocess.Popen(args, start_new_session=True, **kwargs)
        return
    pythonw = os.path.join(os.path.dirname(args[0]), "pythonw.exe")
    if os.path.exists(pythonw):
        args = [pythonw] + args[1:]  # no console window flashing up
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(args, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs)
    except OSError:
        # Claude Code's job object may forbid breaking away; run inside it.
        subprocess.Popen(args, creationflags=flags, **kwargs)


def start_learner(payload) -> None:
    """Start usage_learn.py in the background when the model is due.

    Throttled by the model file's age and by a lock taken here, before the
    spawn: renders come in bursts, and each would otherwise start its own copy.
    The learner removes the lock when it's done.
    """
    if not has_limits(payload):
        return  # nothing new to learn from
    try:
        if time.time() - os.path.getmtime(claude_path(MODEL_NAME)) < LEARN_EVERY_SECONDS:
            return
    except OSError:
        pass  # no model yet
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage_learn.py")
    if not os.path.exists(script):
        return
    lock = claude_path(LEARN_LOCK_NAME)
    try:
        if time.time() - os.path.getmtime(lock) < LEARN_LOCK_STALE_SECONDS:
            return
        os.unlink(lock)
    except OSError:
        pass  # no lock, or another render just cleared the stale one
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        return  # another render got there first
    try:
        spawn_detached([sys.executable, script, "--background"])
    except Exception:
        try:
            os.unlink(lock)
        except OSError:
            pass


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
    append_history(data, time.time())
    sys.stdout.write(build_line(data))
    try:
        start_learner(data)
    except Exception:
        pass  # learning is optional; the status line is not


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Absolute last resort: emit something harmless, never a traceback.
        try:
            sys.stdout.write("claude")
        except Exception:
            pass
