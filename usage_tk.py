"""Tk canvas drawing shared by overlay.pyw and chooser.pyw.

Standard library only -- no Pillow -- so the overlay and the chooser stay
runnable without the tray's dependencies.

Every routine clears the canvas and draws one figure sized to `size`, so the
same code produces both the live widget and the chooser previews. If a preset
looks right in the chooser, it looks right on the desktop.
"""
import math


def blend(colour, toward, amount):
    """Mix two '#rrggbb' colours: amount 0 keeps `colour`, 1 gives `toward`."""
    a = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(toward[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * amount)) for x, y in zip(a, b))


def rounded_rect(canvas, x0, y0, x1, y1, r, **kw):
    """Tk has no rounded rectangle; approximate one with a smoothed polygon."""
    pts = [
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


def draw_badge(canvas, size, pct, colour, ghost=False, font=None):
    """Filled tile with the number, or -- ghosting -- just the coloured number."""
    canvas.delete("all")
    text = "--" if pct is None else ("99+" if pct >= 100 else str(int(pct)))

    if ghost:
        fill = colour
    else:
        rounded_rect(canvas, 2, 2, size - 2, size - 2, size * 0.22, fill=colour, outline="")
        fill = "#ffffff"

    canvas.create_text(size / 2.0, size / 2.0, text=text, fill=fill,
                       font=font or ("TkDefaultFont", max(8, int(size * 0.34)), "bold"))


def draw_bucket(canvas, size, pct, colour, line_width=3, projection=None):
    """Tapered pail that fills from the bottom.

    `projection` is (typical level, worst level, band colour, mark colour): a
    band from the fill up to where a typical run would take it, and a line
    across the pail where a bad one would. Levels past 100 stop at the rim.

    Ghost mode needs no special case: the pail is already just an outline plus
    its fill level, with nothing behind it to remove.
    """
    canvas.delete("all")
    top_y, bot_y = 0.09 * size, 0.93 * size
    half_top, half_bot = 0.38 * size, 0.26 * size
    cx = size / 2.0

    for a, b in (((cx - half_top, top_y), (cx + half_top, top_y)),
                 ((cx + half_top, top_y), (cx + half_bot, bot_y)),
                 ((cx + half_bot, bot_y), (cx - half_bot, bot_y)),
                 ((cx - half_bot, bot_y), (cx - half_top, top_y))):
        canvas.create_line(a[0], a[1], b[0], b[1], fill=colour,
                           width=line_width, capstyle="round")

    inset = max(2.0, 0.06 * size)
    bottom, top = bot_y - inset, top_y + inset

    def surface(level):
        """Height of the liquid at `level`% and the pail's half-width there."""
        y = bottom - (bottom - top) * (max(0.0, min(100.0, level)) / 100.0)
        # Taper: the pail narrows lower down, so the liquid surface must too.
        frac = ((bot_y - y) / float(bot_y - top_y)) if bot_y > top_y else 0.0
        return y, half_bot + (half_top - half_bot) * frac

    def fill_between(lo, hi, fill):
        if hi <= lo:
            return
        (y0, w0), (y1, w1) = surface(lo), surface(hi)
        canvas.create_polygon(cx - w1 + inset, y1, cx + w1 - inset, y1,
                              cx + w0 - inset, y0, cx - w0 + inset, y0,
                              fill=fill, outline="")

    level = 0 if pct is None else max(0, min(100, pct))
    if projection:
        fill_between(level, projection[0], projection[2])
    fill_between(0, level, colour)
    if projection and projection[1] > level:
        y, half = surface(projection[1])
        canvas.create_line(cx - half, y, cx + half, y, fill=projection[3],
                           width=line_width, capstyle="round")


def draw_pie(canvas, size, pct, colour, hole_bg, show_track=True,
             track="#3d3d42", line_width=3, projection=None):
    """Donut dial sweeping clockwise from 12 o'clock.

    `projection` is (typical level, worst level, band colour, mark colour): the
    dial carries on past the used arc in the band colour up to a typical run,
    and a tick across the ring marks a bad one. Levels past 100 stop at 12.

    With show_track off (ghost mode) the grey ring is omitted, leaving only the
    used arc floating on whatever is behind the window.
    """
    canvas.delete("all")
    pad = max(2, int(round(line_width)))
    box = (pad, pad, size - pad, size - pad)

    if show_track:
        canvas.create_oval(*box, fill=track, outline="")

    def sweep(lo, hi, fill):
        # Tk sweeps counter-clockwise, so negate the extent to run clockwise
        # from 12 o'clock (start=90). A full 360 would draw nothing.
        if hi > lo:
            canvas.create_arc(*box, start=90 - lo * 3.6, extent=-min(359.9, (hi - lo) * 3.6),
                              fill=fill, outline="", style="pieslice")

    level = 0 if pct is None else max(0, min(100, pct))
    if projection:
        sweep(level, min(100, projection[0]), projection[2])
    sweep(0, level, colour)
    if level <= 0 and not show_track and not (projection and projection[0] > 0):
        # Nothing to sweep and no track: outline it so the figure isn't blank.
        canvas.create_oval(*box, outline=colour, width=line_width)

    hole = size * 0.29
    canvas.create_oval(hole, hole, size - hole, size - hole,
                       fill=hole_bg, outline="")

    if projection and projection[1] > level:
        angle = math.radians(90 - min(100, projection[1]) * 3.6)
        centre = size / 2.0
        inner, outer = centre - hole, centre - pad
        dx, dy = math.cos(angle), -math.sin(angle)
        canvas.create_line(centre + inner * dx, centre + inner * dy,
                           centre + outer * dx, centre + outer * dy,
                           fill=projection[3], width=line_width, capstyle="round")
