"""System-tray indicator mirroring Claude subscription usage.

Reads the local mirror file written by statusline.py every 5 seconds and
renders the 5-hour usage percentage as the tray icon. Tooltip shows both the
5-hour and 7-day windows plus time until each resets.

This process makes no network calls and reads no credentials. Its only input is
the local mirror file. It costs nothing to run -- it is a passive visualizer.

Windows:  pythonw.exe tray.pyw
macOS:    python3 tray.pyw     (needs pyobjc; see requirements.txt)
"""
import os
import sys
import threading
import webbrowser

from PIL import Image, ImageDraw, ImageFont
import pystray

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_core as core

POLL_SECONDS = 5
ICON_SIZE = 64
COLOR_TEXT = (255, 255, 255)

# Windows tray tooltips are capped at 127 characters.
TOOLTIP_MAX = 126

_FONT_CACHE = {}


def load_font(size: int):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    font = None
    for name in ("segoeuib.ttf", "arialbd.ttf", "seguisb.ttf", "Arial Bold.ttf",
                 "Helvetica.ttc", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, size)
            break
        except Exception:
            continue
    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
    _FONT_CACHE[size] = font
    return font


def _centre_text(draw, text, font, box=None):
    """Top-left coords that centre `text` inside `box` (default: whole icon)."""
    x0, y0, x1, y1 = box or (0, 0, ICON_SIZE, ICON_SIZE)
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return (x0 + (x1 - x0 - (right - left)) / 2 - left,
                y0 + (y1 - y0 - (bottom - top)) / 2 - top)
    except Exception:
        return (x0 + (x1 - x0) / 4, y0 + (y1 - y0) / 4)


def draw_badge(draw, pct, colour, ghost=False) -> None:
    """Rounded square with the percentage number centred in it.

    In ghost mode the tile is dropped and the number itself carries the colour,
    outlined so it stays legible on both light and dark taskbars.
    """
    if not ghost:
        draw.rounded_rectangle((2, 2, ICON_SIZE - 3, ICON_SIZE - 3), radius=14, fill=colour + (255,))

    if pct is None:
        text = "--"
    elif pct >= 100:
        text = "99+"
    else:
        text = str(pct)

    font = load_font(44 if len(text) <= 2 else 32)
    pos = _centre_text(draw, text, font)

    if ghost:
        try:
            draw.text(pos, text, font=font, fill=colour + (255,),
                      stroke_width=3, stroke_fill=(0, 0, 0, 170))
            return
        except TypeError:
            pass  # Pillow too old for stroke_width; fall through to plain text.
        draw.text(pos, text, font=font, fill=colour + (255,))
    else:
        draw.text(pos, text, font=font, fill=COLOR_TEXT + (255,))


def draw_bucket(draw, pct, colour) -> None:
    """Tapered pail that fills from the bottom as usage climbs."""
    top_y, bot_y = 6, ICON_SIZE - 5
    half_top, half_bot = 25.0, 17.0
    cx = ICON_SIZE / 2.0

    outline = colour + (255,)
    walls = [(cx - half_top, top_y), (cx + half_top, top_y),
             (cx + half_bot, bot_y), (cx - half_bot, bot_y)]
    draw.line(walls[0:2], fill=outline, width=4)          # rim
    draw.line([walls[1], walls[2]], fill=outline, width=4)  # right wall
    draw.line([walls[2], walls[3]], fill=outline, width=4)  # base
    draw.line([walls[3], walls[0]], fill=outline, width=4)  # left wall

    level = 0 if pct is None else max(0, min(100, pct))
    if level <= 0:
        return

    inset = 4.0
    span = (bot_y - inset) - (top_y + inset)
    fill_y = (bot_y - inset) - span * (level / 100.0)
    # Taper: the pail is narrower lower down, so the liquid surface must be too.
    frac = ((bot_y - fill_y) / float(bot_y - top_y)) if bot_y > top_y else 0.0
    half_at_fill = (half_bot + (half_top - half_bot) * frac) - inset
    half_at_base = half_bot - inset

    draw.polygon([(cx - half_at_fill, fill_y), (cx + half_at_fill, fill_y),
                  (cx + half_at_base, bot_y - inset), (cx - half_at_base, bot_y - inset)],
                 fill=colour + (255,))


def draw_pie(draw, pct, colour, ghost=False) -> None:
    """Donut dial sweeping clockwise from 12 o'clock.

    Ghost mode drops the grey track ring, leaving only the used arc.
    """
    box = (4, 4, ICON_SIZE - 5, ICON_SIZE - 5)
    if not ghost:
        draw.ellipse(box, fill=(58, 58, 62, 255))

    level = 0 if pct is None else max(0, min(100, pct))
    if level > 0:
        # -90 puts the start at 12 o'clock; PIL sweeps clockwise from there.
        draw.pieslice(box, -90, -90 + level * 3.6, fill=colour + (255,))
    elif ghost:
        # Nothing to sweep and no track: outline it so the icon isn't blank.
        draw.ellipse(box, outline=colour + (255,), width=3)

    hole = (ICON_SIZE * 0.30, ICON_SIZE * 0.30, ICON_SIZE * 0.70, ICON_SIZE * 0.70)
    draw.ellipse(hole, fill=(0, 0, 0, 0))  # punch through to transparent


def draw_icon(pct, stale: bool, style: str = None, ghost: bool = False) -> Image.Image:
    """Render the icon in the selected preset. Falls back to badge on anything
    unrecognised, so a bad config can never leave the tray blank."""
    if style not in core.STYLES:
        style = core.DEFAULT_STYLE

    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    colour = core.pick_color(pct, stale)

    if style == "bucket":
        # The pail is already just an outline plus its fill level -- there is no
        # backdrop to remove, so ghost mode leaves it unchanged.
        draw_bucket(draw, pct, colour)
    elif style == "pie":
        draw_pie(draw, pct, colour, ghost)
    else:
        draw_badge(draw, pct, colour, ghost)
    return img


class TrayApp:
    def __init__(self):
        self._stop = threading.Event()
        self.style = core.get_style()
        self.ghost = core.get_ghost()
        self.icon = pystray.Icon(
            "claude_usage",
            icon=draw_icon(None, True, self.style, self.ghost),
            title="Claude usage (starting...)",
            menu=pystray.Menu(
                pystray.MenuItem("Open usage page", self.on_open, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Style", pystray.Menu(*[
                    pystray.MenuItem(
                        core.STYLE_LABELS[s],
                        self._make_style_setter(s),
                        checked=self._make_style_check(s),
                        radio=True,
                    ) for s in core.STYLES
                ])),
                pystray.MenuItem("Ghost mode", self.on_ghost,
                                 checked=lambda item: self.ghost),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self.on_quit),
            ),
        )
        self._last = None  # (pct, stale, style) of the last drawn icon

    def _make_style_setter(self, style):
        def setter(icon=None, item=None):
            self.style = core.set_style(style)
            self._last = None  # force a redraw in the new style
            try:
                self.refresh()
            except Exception:
                pass
        return setter

    def _make_style_check(self, style):
        return lambda item: self.style == style

    def on_ghost(self, icon=None, item=None):
        self.ghost = core.set_ghost(not self.ghost)
        self._last = None  # force a redraw
        try:
            self.refresh()
        except Exception:
            pass

    def on_open(self, icon=None, item=None):
        try:
            webbrowser.open(core.USAGE_URL)
        except Exception:
            pass

    def on_quit(self, icon=None, item=None):
        self._stop.set()
        try:
            self.icon.stop()
        except Exception:
            pass

    def refresh(self) -> None:
        state = core.read_state()
        # Pick up appearance changed by the overlay (or a hand edit), no restart.
        cfg = core.load_config()
        self.style = core.get_style(cfg)
        self.ghost = core.get_ghost(cfg)
        key = (state.five_pct, state.stale, self.style, self.ghost)
        if key != self._last:
            # Redraw only when something visible actually changed.
            try:
                self.icon.icon = draw_icon(state.five_pct, state.stale, self.style, self.ghost)
                self._last = key
            except Exception:
                pass
        try:
            self.icon.title = core.build_tooltip(state)[:TOOLTIP_MAX]
        except Exception:
            pass

    def _loop(self, icon) -> None:
        icon.visible = True
        while not self._stop.is_set():
            try:
                self.refresh()
            except Exception:
                pass  # A bad poll must never kill the tray.
            self._stop.wait(POLL_SECONDS)

    def run(self) -> None:
        self.icon.run(setup=self._loop)


if __name__ == "__main__":
    TrayApp().run()
