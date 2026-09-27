"""Shared logic for reading the usage mirror. Imported by tray.pyw and overlay.pyw.

No network calls, no credentials, no API key. The only input is the local file
written by statusline.py.
"""
import datetime
import json
import os
import time

STALE_SECONDS = 600  # 10 minutes -> grey out
USAGE_URL = "https://claude.ai/settings/usage"

# Visualizer presets. Shared by the tray icon and the desktop overlay so both
# follow whichever one you pick.
STYLES = ("badge", "bucket", "pie")
DEFAULT_STYLE = "badge"
STYLE_LABELS = {
    "badge": "Badge (number)",
    "bucket": "Bucket (fills up)",
    "pie": "Pie (round dial)",
}
CONFIG_NAME = "usage-visualizer.json"

# Appearance bounds. Clamped on read as well as write, so a hand-edited config
# can't produce a 4000-pixel widget or an invisible one.
SCALE_MIN, SCALE_MAX, SCALE_DEFAULT = 0.6, 2.5, 1.0
ALPHA_MIN, ALPHA_MAX, ALPHA_DEFAULT = 0.25, 1.0, 0.92

COLOR_OK = (46, 160, 67)       # green      0%
COLOR_WARN = (210, 153, 34)    # amber     50%
COLOR_HIGH = (219, 109, 40)    # orange    75%
COLOR_CRIT = (218, 54, 51)     # red       90%
COLOR_MAX = (124, 16, 22)      # dark red 100%
COLOR_STALE = (110, 110, 110)  # grey      stale / unknown

# Anchor points for a continuous colour ramp. Between any two stops the colour
# is interpolated, so 98% reads visibly darker than 90% instead of both landing
# on the same flat red.
COLOR_STOPS = (
    (0, COLOR_OK),
    (50, COLOR_WARN),
    (75, COLOR_HIGH),
    (90, COLOR_CRIT),
    (100, COLOR_MAX),
)


def claude_dir() -> str:
    base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(base, ".claude")


def mirror_path() -> str:
    return os.path.join(claude_dir(), "usage-mirror.json")


def config_path() -> str:
    return os.path.join(claude_dir(), CONFIG_NAME)


def load_config() -> dict:
    """Shared settings (style, overlay position). Never raises."""
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        os.makedirs(claude_dir(), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
    except Exception:
        pass  # Losing a saved preference is not worth crashing over.


def get_style(cfg=None) -> str:
    """Current preset, validated against STYLES so a hand-edited config that
    says 'banana' falls back instead of breaking the renderer."""
    if cfg is None:
        cfg = load_config()
    style = cfg.get("style")
    return style if style in STYLES else DEFAULT_STYLE


def set_style(style: str) -> str:
    if style not in STYLES:
        return get_style()
    cfg = load_config()
    cfg["style"] = style
    save_config(cfg)
    return style


def _clamped(value, lo, hi, default):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def get_scale(cfg=None) -> float:
    if cfg is None:
        cfg = load_config()
    return _clamped(cfg.get("scale", SCALE_DEFAULT), SCALE_MIN, SCALE_MAX, SCALE_DEFAULT)


def set_scale(value) -> float:
    cfg = load_config()
    scale = _clamped(value, SCALE_MIN, SCALE_MAX, SCALE_DEFAULT)
    cfg["scale"] = round(scale, 3)
    save_config(cfg)
    return scale


def get_alpha(cfg=None) -> float:
    if cfg is None:
        cfg = load_config()
    return _clamped(cfg.get("alpha", ALPHA_DEFAULT), ALPHA_MIN, ALPHA_MAX, ALPHA_DEFAULT)


def set_alpha(value) -> float:
    cfg = load_config()
    alpha = _clamped(value, ALPHA_MIN, ALPHA_MAX, ALPHA_DEFAULT)
    cfg["alpha"] = round(alpha, 3)
    save_config(cfg)
    return alpha


def get_ghost(cfg=None) -> bool:
    """Ghost mode: no panel behind the figure, just the drawing itself."""
    if cfg is None:
        cfg = load_config()
    return bool(cfg.get("ghost", False))


def set_ghost(value) -> bool:
    cfg = load_config()
    cfg["ghost"] = bool(value)
    save_config(cfg)
    return bool(value)


def get_folded(cfg=None) -> bool:
    """Overlay folded down to its header line."""
    if cfg is None:
        cfg = load_config()
    return bool(cfg.get("folded", False))


def set_folded(value) -> bool:
    cfg = load_config()
    cfg["folded"] = bool(value)
    save_config(cfg)
    return bool(value)


def dig(data, *keys):
    """Nested lookup that returns None instead of raising on any missing link."""
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def as_pct(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return max(0, min(100, int(round(value))))
    except Exception:
        return None


def as_ts(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def fmt_countdown(resets_at) -> str:
    """'resets in 2h 13m', or a plain marker when unknown/elapsed."""
    if resets_at is None:
        return "reset unknown"
    delta = resets_at - time.time()
    if delta <= 0:
        return "resetting"
    hours, rem = divmod(int(delta), 3600)
    minutes = rem // 60
    if hours:
        return "resets in %dh %02dm" % (hours, minutes)
    if minutes:
        return "resets in %dm" % minutes
    return "resets in <1m"


def fmt_short(resets_at) -> str:
    """Compact '2h 04m' for the overlay, where space is tight."""
    if resets_at is None:
        return "--"
    delta = resets_at - time.time()
    if delta <= 0:
        return "now"
    hours, rem = divmod(int(delta), 3600)
    minutes = rem // 60
    if hours:
        return "%dh %02dm" % (hours, minutes)
    return "%dm" % max(1, minutes)


def fmt_clock(resets_at) -> str:
    """Wall-clock reset time: '14:10' today, 'Tue 23:00' later this week,
    '28 Jul 23:00' beyond that. Saves doing the arithmetic yourself."""
    if resets_at is None:
        return "--"
    try:
        when = datetime.datetime.fromtimestamp(resets_at)
    except (ValueError, OSError, OverflowError):
        return "--"

    today = datetime.date.today()
    days = (when.date() - today).days
    if days <= 0:
        return when.strftime("%H:%M")
    if days < 7:
        return when.strftime("%a %H:%M")
    return when.strftime("%d %b %H:%M")


def fmt_age(captured_at) -> str:
    age = max(0, int(time.time() - captured_at))
    if age < 60:
        return "%ds ago" % age
    if age < 3600:
        return "%dm ago" % (age // 60)
    return "%dh %dm ago" % (age // 3600, (age % 3600) // 60)


class UsageState:
    """Snapshot of what should be on screen right now."""

    def __init__(self):
        self.five_pct = None
        self.five_reset = None
        self.seven_pct = None
        self.seven_reset = None
        self.model = None
        self.five_rolled = False   # reset time has passed; see read_state
        self.seven_rolled = False
        self.captured_at = None
        self.stale = True
        self.problem = "waiting for Claude Code"

    @property
    def has_limits(self) -> bool:
        return self.five_pct is not None or self.seven_pct is not None


def read_state() -> UsageState:
    """Read the mirror. Never raises; degrades to a state carrying `.problem`."""
    state = UsageState()

    try:
        with open(mirror_path(), "r", encoding="utf-8") as fh:
            record = json.load(fh)
    except FileNotFoundError:
        state.problem = "no mirror file yet - is statusline.py installed?"
        return state
    except Exception:
        state.problem = "mirror file unreadable"
        return state

    if not isinstance(record, dict):
        state.problem = "mirror file malformed"
        return state

    # limits_at is when the numbers were last actually reported; captured_at
    # only says some session rendered. Older mirrors have just captured_at.
    state.captured_at = as_ts(record.get("limits_at", record.get("captured_at")))
    now = time.time()
    if state.captured_at is not None:
        state.stale = (now - state.captured_at) > STALE_SECONDS

    payload = record.get("payload")
    if not isinstance(payload, dict):
        state.problem = "no payload captured"
        return state

    state.model = dig(payload, "model", "display_name")
    state.five_pct = as_pct(dig(payload, "rate_limits", "five_hour", "used_percentage"))
    state.five_reset = as_ts(dig(payload, "rate_limits", "five_hour", "resets_at"))
    state.seven_pct = as_pct(dig(payload, "rate_limits", "seven_day", "used_percentage"))
    state.seven_reset = as_ts(dig(payload, "rate_limits", "seven_day", "resets_at"))

    # Past its reset, a window's old number is known to be wrong: that usage is
    # gone. Show 0% until Claude Code reports the new window. That's a floor --
    # claude.ai use counts too and is invisible here -- but a far better one
    # than the old high number. It also makes an idle 5h reading fresh again.
    if state.five_pct is not None and state.five_reset is not None and state.five_reset <= now:
        state.five_pct, state.five_rolled = 0, True
        state.stale = False
    if state.seven_pct is not None and state.seven_reset is not None and state.seven_reset <= now:
        state.seven_pct, state.seven_rolled = 0, True

    if not state.has_limits:
        # Expected under API-key auth, and right after /clear before the first
        # API response of the session.
        state.problem = "no rate_limits in payload (API-key auth, or session not started yet)"
    else:
        state.problem = None

    return state


def pick_color(pct, stale: bool):
    """Continuous green -> amber -> orange -> red -> dark red ramp.

    Stale numbers keep their colour, faded halfway to grey. Usage only rises
    while you use Claude, so an idle reading is usually still right; the fade
    says "old" without hiding how full the window was.
    """
    if pct is None:
        return COLOR_STALE

    pct = max(0, min(100, pct))
    rgb = COLOR_MAX
    lo_at, lo_rgb = COLOR_STOPS[0]
    for hi_at, hi_rgb in COLOR_STOPS[1:]:
        if pct <= hi_at:
            span = hi_at - lo_at
            t = 0.0 if span <= 0 else (pct - lo_at) / float(span)
            rgb = tuple(int(round(lo_rgb[i] + (hi_rgb[i] - lo_rgb[i]) * t)) for i in range(3))
            break
        lo_at, lo_rgb = hi_at, hi_rgb
    if stale:
        rgb = tuple(int(round((a + b) / 2.0)) for a, b in zip(rgb, COLOR_STALE))
    return rgb


def to_hex(rgb) -> str:
    return "#%02x%02x%02x" % rgb


def build_tooltip(state: UsageState, est=None, pace=None, limit=None) -> str:
    """Multi-line summary used by the tray tooltip, the overlay hover text and
    `claude-usage.sh status`.

    `limit` caps the length (Windows tray tooltips stop at 127 characters):
    lines are dropped least important first -- model, header, the "updated"
    age while fresh -- rather than cutting the text off mid-line.
    """
    lines = [(5, "Claude usage")]  # (drop order: higher goes first, text)
    said_problem = False

    if state.has_limits:
        if state.five_rolled:
            lines.append((0, "5h  0%%   reset at %s, new window" % fmt_clock(state.five_reset)))
        elif state.five_pct is not None:
            lines.append((0, "5h  %d%%   resets %s  (%s)" % (
                state.five_pct, fmt_clock(state.five_reset), fmt_short(state.five_reset))))
        if state.seven_rolled:
            lines.append((2, "7d  0%%   reset at %s, new window" % fmt_clock(state.seven_reset)))
        elif state.seven_pct is not None:
            lines.append((2, "7d  %d%%   resets %s  (%s)" % (
                state.seven_pct, fmt_clock(state.seven_reset), fmt_short(state.seven_reset))))
    else:
        lines.append((0, state.problem or "no usage data"))
        said_problem = True

    if pace:
        lines.append((3, pace_text(pace, long=True)))
    if est:
        lines.append((3, estimate_text(est)))

    if state.captured_at is not None:
        # Knowing the data is old matters more than most of the rest.
        lines.append((1 if state.stale else 4, "Updated %s%s" % (
            fmt_age(state.captured_at), "  [STALE]" if state.stale else "")))
    elif state.problem and not said_problem:
        lines.append((1, state.problem))

    if state.model:
        lines.append((6, state.model))

    def joined():
        return "\n".join(text for _rank, text in lines)

    while limit and len(joined()) > limit and len(lines) > 1:
        worst = max(range(len(lines)), key=lambda i: (lines[i][0], i))
        del lines[worst]
    return joined()[:limit] if limit else joined()


# --- pace (from statusline.py's usage-history.jsonl) ------------------------

HISTORY_NAME = "usage-history.jsonl"
PACE_LOOKBACK = 60 * 60   # judge the pace on the last hour of work
PACE_IDLE = 15 * 60       # no rise for this long: not working, no pace
PACE_MIN_SPAN = 10 * 60   # shorter than this is noise
PACE_MIN_RISE = 2         # percentage points
_history_cache = {"key": None, "records": []}


def history_tail(max_bytes=32768) -> list:
    """The last few hundred history records, oldest first. Cached on the file's
    size and mtime, so polling every few seconds costs a stat. Never raises."""
    path = os.path.join(claude_dir(), HISTORY_NAME)
    try:
        st = os.stat(path)
    except OSError:
        return []
    key = (st.st_size, st.st_mtime)
    if _history_cache["key"] == key:
        return _history_cache["records"]
    records = []
    try:
        with open(path, "rb") as fh:
            fh.seek(max(0, st.st_size - max_bytes))
            for line in fh.read().decode("utf-8", "replace").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # the cut-off first line, or a torn write
                if isinstance(rec, dict) and as_ts(rec.get("t")) is not None:
                    records.append(rec)
    except OSError:
        return []
    records.sort(key=lambda r: r["t"])
    _history_cache.update(key=key, records=records)
    return records


def pace(state: UsageState, records=None, now=None):
    """Where the 5-hour window is heading at the pace of the last hour.

    None unless there's a real trend to report: you're working right now (a
    rise in the last 15 minutes) and usage climbed at least 2 points over at
    least 10 minutes of this window. Otherwise a dict: per_hour (points),
    full_at (when it would hit 100%) and short (True if that's before the reset).
    """
    if state.five_rolled or state.five_pct is None or state.five_reset is None:
        return None
    now = time.time() if now is None else now
    records = history_tail() if records is None else records
    window = [r for r in records
              if as_ts(r.get("5h")) is not None
              and abs((as_ts(r.get("5h_reset")) or 0) - state.five_reset) <= 600
              and now - PACE_LOOKBACK <= r["t"] <= now]
    if len(window) < 2 or now - window[-1]["t"] > PACE_IDLE:
        return None
    first, last = window[0], window[-1]
    span, rise = last["t"] - first["t"], last["5h"] - first["5h"]
    if span < PACE_MIN_SPAN or rise < PACE_MIN_RISE:
        return None
    per_sec = rise / float(span)
    full_at = last["t"] + max(0, 100 - state.five_pct) / per_sec
    return {"per_hour": per_sec * 3600, "full_at": full_at,
            "short": full_at < state.five_reset}


def pace_text(p, long=False) -> str:
    """'↗ full ~14:50' when the pace runs out before the reset, else how fast
    it's going. `long` adds the context the tooltip has room for."""
    if p["short"]:
        text = "Pace: full by ~%s" if long else "↗ full ~%s"
        return text % fmt_clock(p["full_at"])
    text = "Pace +%d%%/h: lasts to reset" if long else "+%d%%/h, lasts"
    return text % round(p["per_hour"])


# --- run estimates (from usage_learn.py's model) -------------------------------

MODEL_NAME = "usage-model.json"
ESTIMATE_OFF = "off"
DEFAULT_ESTIMATE_FOR = "workflow"
FITS, TIGHT, CUT_OFF = "fits", "tight", "likely cut off"
VERDICT_COLORS = {FITS: COLOR_OK, TIGHT: COLOR_WARN, CUT_OFF: COLOR_CRIT}
VERDICT_RANK = {FITS: 0, TIGHT: 1, CUT_OFF: 2}


def model_path() -> str:
    return os.path.join(claude_dir(), MODEL_NAME)


def load_model() -> dict:
    """What usage_learn.py has learned, or {} if nothing yet. Never raises."""
    try:
        with open(model_path(), "r", encoding="utf-8") as fh:
            model = json.load(fh)
    except Exception:
        return {}
    return model if isinstance(model, dict) else {}


def run_types(model) -> list:
    """Run types the model has costs for: 'workflow' first, then most frequent."""
    costs = model.get("run_costs") if isinstance(model, dict) else None
    if not isinstance(costs, dict):
        return []
    return sorted((group for group, stats in costs.items() if isinstance(stats, dict)),
                  key=lambda group: (group != "workflow", -(as_ts(costs[group].get("n")) or 0), group))


def get_estimate_for(cfg=None) -> str:
    """Run type the visualizers estimate for, or ESTIMATE_OFF."""
    if cfg is None:
        cfg = load_config()
    value = cfg.get("estimate_for")
    return value if isinstance(value, str) and value else DEFAULT_ESTIMATE_FOR


def set_estimate_for(value: str) -> str:
    cfg = load_config()
    cfg["estimate_for"] = value
    save_config(cfg)
    return value


def fit(typical: float, worst: float, left: float) -> str:
    """FITS: even a bad run fits in what's left. TIGHT: a typical one does, a
    bad one wouldn't. CUT_OFF: not even a typical one does."""
    if worst <= left:
        return FITS
    return TIGHT if typical <= left else CUT_OFF


def estimate_run(state: UsageState, model: dict, group: str):
    """How a run of `group` would land on current usage, as a dict, or None
    when there's nothing honest to say: stale or missing numbers, no learned
    rate, or no finished runs of that type yet.

    The verdict comes from whichever window is worse off. five_typical and
    five_worst are the 5-hour shares for drawing on the figure (None when the
    5-hour rate isn't learned yet).
    """
    if state.stale or not state.has_limits or not group or group == ESTIMATE_OFF:
        return None
    stats = dig(model, "run_costs", group)
    if not isinstance(stats, dict):
        return None
    median, p90 = as_ts(stats.get("median_usd")), as_ts(stats.get("p90_usd"))
    if median is None or p90 is None:
        return None

    windows = []
    for key, used, reset in (("5h", state.five_pct, state.five_reset),
                             ("7d", state.seven_pct, state.seven_reset)):
        per = as_ts(dig(model, "rates", key, "usd_per_pct"))
        if not per or per <= 0 or used is None:
            continue
        typical, worst = median / per, p90 / per
        windows.append({"window": key, "typical": typical, "worst": worst, "reset": reset,
                        "verdict": fit(typical, worst, 100 - used)})
    if not windows:
        return None

    limiting = max(windows, key=lambda w: (VERDICT_RANK[w["verdict"]], w["typical"]))
    five = next((w for w in windows if w["window"] == "5h"), None)
    return {
        "group": group,
        "label": group.split(": ", 1)[-1][:14],
        "verdict": limiting["verdict"],
        "window": limiting["window"],
        "typical": limiting["typical"],
        "worst": limiting["worst"],
        "reset": limiting["reset"],
        "five_typical": five["typical"] if five else None,
        "five_worst": five["worst"] if five else None,
    }


def verdict_color(verdict):
    return VERDICT_COLORS.get(verdict, COLOR_STALE)


def estimate_text(est) -> str:
    """One short line: '✓ workflow ~16% fits', '⚠ workflow 16-47% tight',
    '⚠ workflow: wait for 20:40'. The symbol carries the verdict wherever the
    colour can't (e.g. on the coloured badge tile)."""
    def share(value):
        return "<1%" if value < 1 else "%d%%" % round(value)

    if est["verdict"] == CUT_OFF:
        return "⚠ %s: wait for %s" % (est["label"], fmt_clock(est["reset"]))
    if est["verdict"] == TIGHT:
        return "⚠ %s %s-%s tight" % (est["label"], share(est["typical"]).rstrip("%"), share(est["worst"]))
    return "✓ %s ~%s fits" % (est["label"], share(est["typical"]))
