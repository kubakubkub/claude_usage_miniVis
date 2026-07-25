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

    state.captured_at = as_ts(record.get("captured_at"))
    if state.captured_at is not None:
        state.stale = (time.time() - state.captured_at) > STALE_SECONDS

    payload = record.get("payload")
    if not isinstance(payload, dict):
        state.problem = "no payload captured"
        return state

    state.model = dig(payload, "model", "display_name")
    state.five_pct = as_pct(dig(payload, "rate_limits", "five_hour", "used_percentage"))
    state.five_reset = as_ts(dig(payload, "rate_limits", "five_hour", "resets_at"))
    state.seven_pct = as_pct(dig(payload, "rate_limits", "seven_day", "used_percentage"))
    state.seven_reset = as_ts(dig(payload, "rate_limits", "seven_day", "resets_at"))

    if not state.has_limits:
        # Expected under API-key auth, and right after /clear before the first
        # API response of the session.
        state.problem = "no rate_limits in payload (API-key auth, or session not started yet)"
    else:
        state.problem = None

    return state


def pick_color(pct, stale: bool):
    """Continuous green -> amber -> orange -> red -> dark red ramp."""
    if stale or pct is None:
        return COLOR_STALE

    pct = max(0, min(100, pct))
    lo_at, lo_rgb = COLOR_STOPS[0]
    for hi_at, hi_rgb in COLOR_STOPS[1:]:
        if pct <= hi_at:
            span = hi_at - lo_at
            t = 0.0 if span <= 0 else (pct - lo_at) / float(span)
            return tuple(int(round(lo_rgb[i] + (hi_rgb[i] - lo_rgb[i]) * t)) for i in range(3))
        lo_at, lo_rgb = hi_at, hi_rgb
    return COLOR_MAX


def to_hex(rgb) -> str:
    return "#%02x%02x%02x" % rgb


def build_tooltip(state: UsageState) -> str:
    """Multi-line summary used by the tray tooltip and the overlay hover text."""
    lines = ["Claude usage"]
    said_problem = False

    if state.has_limits:
        if state.five_pct is not None:
            lines.append("5h  %d%%   resets %s  (%s)" % (
                state.five_pct, fmt_clock(state.five_reset), fmt_short(state.five_reset)))
        if state.seven_pct is not None:
            lines.append("7d  %d%%   resets %s  (%s)" % (
                state.seven_pct, fmt_clock(state.seven_reset), fmt_short(state.seven_reset)))
    else:
        lines.append(state.problem or "no usage data")
        said_problem = True

    # Freshness before model name: the tray tooltip is truncated at 127 chars,
    # and knowing the data is STALE matters more than knowing the model.
    if state.captured_at is not None:
        lines.append("Updated %s%s" % (fmt_age(state.captured_at), "  [STALE]" if state.stale else ""))
    elif state.problem and not said_problem:
        lines.append(state.problem)

    if state.model:
        lines.append(state.model)

    return "\n".join(lines)
