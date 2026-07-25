"""Tk canvas drawing shared by overlay.pyw and chooser.pyw.

Standard library only -- no Pillow -- so the overlay and the chooser stay
runnable without the tray's dependencies.

Every routine clears the canvas and draws one figure sized to `size`, so the
same code produces both the live widget and the chooser previews. If a preset
looks right in the chooser, it looks right on the desktop.
"""


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


def draw_bucket(canvas, size, pct, colour, line_width=3):
    """Tapered pail that fills from the bottom.

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

    level = 0 if pct is None else max(0, min(100, pct))
    if level <= 0:
        return

    inset = max(2.0, 0.06 * size)
    span = (bot_y - inset) - (top_y + inset)
    fill_y = (bot_y - inset) - span * (level / 100.0)
    # Taper: the pail narrows lower down, so the liquid surface must too.
    frac = ((bot_y - fill_y) / float(bot_y - top_y)) if bot_y > top_y else 0.0
    hf = (half_bot + (half_top - half_bot) * frac) - inset
    hb = half_bot - inset
    canvas.create_polygon(cx - hf, fill_y, cx + hf, fill_y,
                          cx + hb, bot_y - inset, cx - hb, bot_y - inset,
                          fill=colour, outline="")


def draw_pie(canvas, size, pct, colour, hole_bg, show_track=True,
             track="#3d3d42", line_width=3):
    """Donut dial sweeping clockwise from 12 o'clock.

    With show_track off (ghost mode) the grey ring is omitted, leaving only the
    used arc floating on whatever is behind the window.
    """
    canvas.delete("all")
    pad = max(2, int(round(line_width)))
    box = (pad, pad, size - pad, size - pad)

    if show_track:
        canvas.create_oval(*box, fill=track, outline="")

    level = 0 if pct is None else max(0, min(100, pct))
    if level > 0:
        # Tk sweeps counter-clockwise, so negate the extent to run clockwise
        # from 12 o'clock (start=90). A full 360 would draw nothing.
        canvas.create_arc(*box, start=90,
                          extent=-(level * 3.6) if level < 100 else -359.9,
                          fill=colour, outline="", style="pieslice")
    elif not show_track:
        # Nothing to sweep and no track: outline it so the figure isn't blank.
        canvas.create_oval(*box, outline=colour, width=line_width)

    hole = size * 0.29
    canvas.create_oval(hole, hole, size - hole, size - hole,
                       fill=hole_bg, outline="")
