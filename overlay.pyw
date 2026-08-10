"""Always-on-top desktop overlay showing Claude subscription usage.

A small frameless widget that floats above the desktop. Drag it anywhere; the
position is remembered. Right-click for the menu, double-click to open the
usage page.

Three presets, switchable live and shared with the tray icon:
  badge   flat tile with the percentage as a big number
  bucket  tapered pail that fills up as usage climbs
  pie     round donut dial

Appearance (right-click -> Appearance...):
  Size        60%-250% slider
  Opacity     25%-100% slider
  Ghost mode  drops the panel entirely -- only the figure and text remain

Uses Tkinter only (Python standard library) -- no pystray, no Pillow -- so it
runs anywhere Python has Tk, including macOS and Linux.

Reads only the local mirror file written by statusline.py. No network calls,
no credentials, no API key. Costs nothing to run.

Windows:  pythonw.exe overlay.pyw
macOS:    python3 overlay.pyw
"""
import os
import sys
import webbrowser

try:
    import tkinter as tk
except Exception:  # pragma: no cover - Tk missing
    sys.stderr.write("tkinter is required. On Debian/Ubuntu: sudo apt install python3-tk\n")
    raise SystemExit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_core as core
import usage_tk as utk

POLL_MS = 5000
BASE_GRAPHIC = 58     # canvas size for bucket / pie at 100%
DARK_BG = "#26262a"   # backdrop for the graphic styles
TRACK = "#3d3d42"     # unfilled portion of the pie
FG_MAIN = "#ffffff"
FG_DIM = "#e6e6e6"
FG_HEAD = "#9a9aa2"
FG_HEAD_ON_COLOUR = "#ffffff"

# Chroma key for ghost mode. Windows renders every pixel of exactly this colour
# fully transparent, which is what removes the panel. Deliberately an odd value
# so nothing we actually draw collides with it.
GHOST_KEY = "#010203"
FG_GHOST_SUB = "#d8d8de"

FONT = "Segoe UI" if sys.platform.startswith("win") else \
       ("Helvetica Neue" if sys.platform == "darwin" else "DejaVu Sans")


class Overlay:
    def __init__(self):
        self.cfg = core.load_config()
        self.style = core.get_style(self.cfg)
        self.scale = core.get_scale(self.cfg)
        self.ghost = core.get_ghost(self.cfg)
        self._ghost_ok = True     # does this platform support -transparentcolor?
        self._settings = None
        self._apply_job = None

        self.root = tk.Tk()
        self.root.title("Claude usage")
        self.root.overrideredirect(True)          # frameless, no taskbar entry
        self.root.attributes("-topmost", True)

        self.frame = tk.Frame(self.root, bg=DARK_BG, padx=10, pady=7)
        self.frame.pack(fill="both", expand=True)

        self._drag = None
        self._moved_to = None
        self._last_key = None

        self._build_menu()
        self._apply_alpha()
        self._apply_ghost()
        self._build_content()

        # Fill in the real text first, so the window is measured at its final
        # size rather than at the width of the "--" placeholder.
        self.refresh()
        self._restore_position()
        # Deferred on purpose -- see _float_above_macos: the window has to be
        # mapped before the level sticks.
        self.root.after(300, self._float_above_macos)
        self.root.after(POLL_MS, self._tick)

    # ---------- appearance helpers ----------

    def _float_above_macos(self):
        """Actually make the badge stay on top on macOS.

        `-topmost` is a no-op under the Tk 8.5 that ships with Apple's system
        Python: measured with CGWindowListCopyWindowInfo, the window still comes
        out at layer 0 (normal), so the badge is created correctly, sits at the
        right coordinates, reports onscreen=True -- and is buried behind every
        ordinary window. It looks exactly like it never launched.

        So we set the NSWindow level ourselves. This runs deferred, via after(),
        because it only takes once the window has actually been mapped: called
        inline during __init__ -- even after update() -- the level is reset and
        the window stays at layer 0.

        REJECTED ALTERNATIVE, do not reintroduce: promoting the window to the
        Aqua `floating` class with ::tk::unsupported::MacWindowStyle also reaches
        layer 3, and looks like the tidier, dependency-free fix. It is not. It
        quietly undoes overrideredirect -- the badge comes back with a full title
        bar and traffic lights, 24px taller, and its content never renders, i.e.
        an empty decorated window. Both the class change and the blank body were
        reproduced directly.

        pyobjc is already a macOS requirement for the tray, but the overlay is
        meant to run on the standard library alone, so a missing AppKit costs
        always-on-top and nothing else.
        """
        if sys.platform != "darwin":
            return
        try:
            import AppKit
            app = AppKit.NSApp()
            if app is None:
                return
            for window in app.windows():
                window.setLevel_(AppKit.NSFloatingWindowLevel)
        except Exception:
            pass

    def _f(self, size):
        """Scale a font size, keeping it legible at the smallest setting."""
        return max(6, int(round(size * self.scale)))

    @property
    def graphic(self):
        return max(24, int(round(BASE_GRAPHIC * self.scale)))

    @property
    def panel_bg(self):
        """Background for panels: the chroma key when ghosting, else dark."""
        return GHOST_KEY if (self.ghost and self._ghost_ok) else DARK_BG

    def _apply_alpha(self):
        try:
            self.root.attributes("-alpha", core.get_alpha(self.cfg))
        except Exception:
            pass

    def _apply_ghost(self):
        """Turn the chroma key on or off.

        -transparentcolor is Windows-only. Where it isn't supported we fall back
        to the normal dark panel rather than leaving a solid block of #010203.
        """
        if self.ghost:
            try:
                self.root.attributes("-transparentcolor", GHOST_KEY)
                self._ghost_ok = True
            except tk.TclError:
                self._ghost_ok = False
        else:
            try:
                self.root.attributes("-transparentcolor", "")
            except tk.TclError:
                pass
        try:
            self.root.configure(bg=self.panel_bg)
        except Exception:
            pass

    # ---------- layout ----------

    def _build_content(self):
        """(Re)create widgets for the current style and size."""
        for child in self.frame.winfo_children():
            child.destroy()
        self.canvas = None

        bg = self.panel_bg
        # The frame itself survives a rebuild, and the badge style tints it with
        # the usage colour. Reset it, or switching to bucket/pie leaves a
        # coloured border around the dark widget where the padding shows through.
        pad = max(4, int(round(10 * self.scale)))
        self.frame.configure(bg=bg, padx=pad, pady=max(3, int(round(7 * self.scale))))

        # Always label it. A filling bucket next to a clock reads as a battery
        # indicator otherwise.
        self.lbl_head = tk.Label(self.frame, text="CLAUDE USAGE", bg=bg, fg=FG_HEAD,
                                 font=(FONT, self._f(7), "bold"))
        self.lbl_head.pack(anchor="w", pady=(0, max(1, int(3 * self.scale))))

        if self.style == "badge":
            self.lbl_pct = tk.Label(self.frame, text="--", bg=bg, fg=FG_MAIN,
                                    font=(FONT, self._f(22), "bold"))
            self.lbl_pct.pack(anchor="w")
            self.lbl_sub = tk.Label(self.frame, text="", bg=bg, fg=FG_DIM,
                                    font=(FONT, self._f(8)), justify="left")
            self.lbl_sub.pack(anchor="w")
        else:
            row = tk.Frame(self.frame, bg=bg)
            row.pack(fill="both", expand=True)
            g = self.graphic
            self.canvas = tk.Canvas(row, width=g, height=g, bg=bg,
                                    highlightthickness=0, bd=0)
            self.canvas.pack(side="left", padx=(0, max(4, int(9 * self.scale))))
            text = tk.Frame(row, bg=bg)
            text.pack(side="left", anchor="center")
            self.lbl_pct = tk.Label(text, text="--", bg=bg, fg=FG_MAIN,
                                    font=(FONT, self._f(15), "bold"))
            self.lbl_pct.pack(anchor="w")
            self.lbl_sub = tk.Label(text, text="", bg=bg, fg=FG_DIM,
                                    font=(FONT, self._f(8)), justify="left")
            self.lbl_sub.pack(anchor="w")

        self._bind_events()
        self._last_key = None  # force a redraw into the new widgets

    def _all_widgets(self):
        out = [self.root]

        def walk(w):
            out.append(w)
            for c in w.winfo_children():
                walk(c)

        walk(self.frame)
        return out

    def _build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Open usage page", command=self.open_usage)
        self.menu.add_separator()

        self._style_var = tk.StringVar(value=self.style)
        styles = tk.Menu(self.menu, tearoff=0)
        for s in core.STYLES:
            styles.add_radiobutton(label=core.STYLE_LABELS[s], value=s,
                                   variable=self._style_var,
                                   command=lambda s=s: self.set_style(s))
        self.menu.add_cascade(label="Style", menu=styles)

        self._ghost_var = tk.BooleanVar(value=self.ghost)
        self.menu.add_checkbutton(label="Ghost mode", variable=self._ghost_var,
                                  command=lambda: self.set_ghost(self._ghost_var.get()))
        self.menu.add_command(label="Appearance...", command=self.open_settings)

        self.menu.add_separator()
        self.menu.add_command(label="Reset position", command=self.reset_position)
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self.quit)

    def _bind_events(self):
        for w in self._all_widgets():
            w.bind("<Button-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<ButtonRelease-1>", self.on_release)
            w.bind("<Double-Button-1>", self.on_double)
            # Button-3 is right-click everywhere; Button-2 is right-click on some Macs.
            w.bind("<Button-3>", self.on_menu)
            w.bind("<Button-2>", self.on_menu)

    def _size(self):
        """Actual window size, falling back to the requested size.

        Before the window is mapped, winfo_width()/winfo_height() return 1 --
        not 0 -- so `or 120` does NOT catch it. Using that 1 would park the
        badge one pixel from the screen edge, i.e. almost entirely off-screen.
        winfo_reqwidth()/reqheight() are valid as soon as geometry is
        calculated, so prefer them whenever the real size isn't known yet.
        """
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        if w <= 1:
            w = self.root.winfo_reqwidth()
        if h <= 1:
            h = self.root.winfo_reqheight()
        return max(int(w), 40), max(int(h), 24)

    def _restore_position(self):
        x = self.cfg.get("x")
        y = self.cfg.get("y")
        w, _h = self._size()
        if not isinstance(x, int) or not isinstance(y, int):
            # Default: top-right, tucked under the usual taskbar/menu bar.
            x, y = max(0, self.root.winfo_screenwidth() - w - 24), 24
        x, y = self._clamp(x, y)
        self.root.geometry("+%d+%d" % (x, y))

    def _clamp(self, x, y):
        """Keep the widget fully on screen even if the display layout changed."""
        w, h = self._size()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        return max(0, min(int(x), sw - w)), max(0, min(int(y), sh - h))

    def _save_position(self, x, y):
        """Persist the position, merging into whatever is on disk right now.

        Writing self.cfg wholesale would clobber a style or ghost change made
        from the tray menu since we last loaded it.
        """
        x, y = int(x), int(y)
        cfg = core.load_config()
        if (cfg.get("x"), cfg.get("y")) == (x, y):
            self.cfg = cfg
            return
        cfg["x"], cfg["y"] = x, y
        core.save_config(cfg)
        self.cfg = cfg

    def _reclamp(self):
        """Re-clamp after a size change, and remember wherever it ended up."""
        x, y = self._clamp(self.root.winfo_x(), self.root.winfo_y())
        self.root.geometry("+%d+%d" % (x, y))
        self._save_position(x, y)

    # ---------- events ----------

    def on_press(self, event):
        self._drag = (event.x_root, event.y_root,
                      self.root.winfo_x(), self.root.winfo_y())
        self._moved_to = None

    def on_drag(self, event):
        if not self._drag:
            return
        sx, sy, ox, oy = self._drag
        nx, ny = ox + event.x_root - sx, oy + event.y_root - sy
        # Remember where we asked the window to go. winfo_x()/winfo_y() lag
        # behind geometry() until the event loop processes the request, so
        # reading them on release can persist the pre-drag position.
        self._moved_to = (nx, ny)
        self.root.geometry("+%d+%d" % (nx, ny))

    def on_release(self, event):
        if not self._drag:
            return
        self._drag = None
        if self._moved_to is not None:
            x, y = self._moved_to
        else:
            self.root.update_idletasks()
            x, y = self.root.winfo_x(), self.root.winfo_y()
        self._moved_to = None
        x, y = self._clamp(x, y)
        self.root.geometry("+%d+%d" % (x, y))
        self._save_position(x, y)

    def on_double(self, event):
        self.open_usage()

    def on_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def open_usage(self):
        try:
            webbrowser.open(core.USAGE_URL)
        except Exception:
            pass

    # ---------- settings ----------

    def set_style(self, style):
        if style not in core.STYLES:
            return
        self.style = core.set_style(style)
        self.cfg = core.load_config()
        self._build_content()
        self.refresh()
        self._reclamp()  # layout size changes between presets

    def set_ghost(self, value):
        self.ghost = core.set_ghost(value)
        self.cfg = core.load_config()
        self._ghost_var.set(self.ghost)
        self._apply_ghost()
        self._build_content()
        self.refresh()
        self._reclamp()

    def set_scale(self, value):
        self.scale = core.set_scale(value)
        self.cfg = core.load_config()
        self._build_content()
        self.refresh()
        self._reclamp()

    def set_alpha(self, value):
        core.set_alpha(value)
        self.cfg = core.load_config()
        self._apply_alpha()

    def _debounced(self, fn, *args):
        """Sliders fire on every pixel; rebuilding that often is wasteful."""
        if self._apply_job is not None:
            try:
                self.root.after_cancel(self._apply_job)
            except Exception:
                pass
        self._apply_job = self.root.after(120, lambda: fn(*args))

    def open_settings(self):
        if self._settings is not None:
            try:
                if self._settings.winfo_exists():
                    self._settings.lift()
                    self._settings.focus_force()
                    return
            except Exception:
                pass

        win = tk.Toplevel(self.root)
        self._settings = win
        win.title("Claude usage - appearance")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.configure(padx=14, pady=12)

        tk.Label(win, text="Size", anchor="w").pack(fill="x")
        size = tk.Scale(win, from_=int(core.SCALE_MIN * 100), to=int(core.SCALE_MAX * 100),
                        orient="horizontal", length=240, resolution=5,
                        command=lambda v: self._debounced(self.set_scale, float(v) / 100.0))
        size.set(int(round(self.scale * 100)))
        size.pack(fill="x")

        tk.Label(win, text="Opacity", anchor="w").pack(fill="x", pady=(8, 0))
        opacity = tk.Scale(win, from_=int(core.ALPHA_MIN * 100), to=100,
                           orient="horizontal", length=240, resolution=5,
                           command=lambda v: self._debounced(self.set_alpha, float(v) / 100.0))
        opacity.set(int(round(core.get_alpha(self.cfg) * 100)))
        opacity.pack(fill="x")

        ghost = tk.BooleanVar(value=self.ghost)
        tk.Checkbutton(win, text="Ghost mode (no background)", variable=ghost, anchor="w",
                       command=lambda: self.set_ghost(ghost.get())).pack(fill="x", pady=(10, 0))

        if not self._ghost_ok:
            tk.Label(win, text="Ghost mode needs Windows; falling back to the dark panel.",
                     fg="#a05020", wraplength=240, justify="left").pack(fill="x")

        tk.Button(win, text="Close", command=win.destroy).pack(anchor="e", pady=(12, 0))

        # Open next to the widget rather than in the screen corner.
        try:
            win.update_idletasks()
            win.geometry("+%d+%d" % (max(0, self.root.winfo_x() - 60),
                                     self.root.winfo_y() + self._size()[1] + 12))
        except Exception:
            pass

    def reset_position(self):
        self.cfg.pop("x", None)
        self.cfg.pop("y", None)
        core.save_config(self.cfg)
        self._restore_position()

    def quit(self):
        # Catch any move that never went through a drag-release (a clamp after a
        # resolution change, say) so the next launch lands in the same spot.
        try:
            self._save_position(self.root.winfo_x(), self.root.winfo_y())
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------- drawing ----------

    def _line_width(self):
        return max(2, int(round(3 * self.scale)))

    def _draw_bucket(self, pct, colour):
        utk.draw_bucket(self.canvas, self.graphic, pct, colour, self._line_width())

    def _draw_pie(self, pct, colour):
        # Ghost mode drops the track ring so only the used arc floats there.
        utk.draw_pie(self.canvas, self.graphic, pct, colour,
                     hole_bg=self.panel_bg,
                     show_track=not (self.ghost and self._ghost_ok),
                     track=TRACK, line_width=self._line_width())

    # ---------- refresh ----------

    def refresh(self):
        state = core.read_state()
        colour = core.to_hex(core.pick_color(state.five_pct, state.stale))
        pct_text = "--" if state.five_pct is None else "%d%%" % state.five_pct

        if state.has_limits:
            # Clock time first -- it's what you plan around; the countdown in
            # brackets saves working out how long that actually is.
            sub = "5h  %s  (%s)" % (core.fmt_clock(state.five_reset),
                                    core.fmt_short(state.five_reset))
            if state.seven_pct is not None:
                sub += "\n7d  %d%%  %s" % (state.seven_pct, core.fmt_clock(state.seven_reset))
            if state.stale:
                sub += "\nSTALE - %s" % core.fmt_age(state.captured_at)
        else:
            sub = "no data\nClaude Code not running?"

        key = (pct_text, sub, colour, self.style, self.ghost, self.scale)
        if key == self._last_key:
            return
        self._last_key = key

        ghosting = self.ghost and self._ghost_ok

        if self.style == "badge":
            # Normally the whole tile carries the colour. Ghosting has no tile,
            # so the number itself becomes the coloured element.
            bg = self.panel_bg if ghosting else colour
            for w in (self.frame, self.lbl_pct, self.lbl_sub, self.lbl_head):
                try:
                    w.configure(bg=bg)
                except Exception:
                    pass
            self.lbl_pct.configure(fg=colour if ghosting else FG_MAIN)
            self.lbl_head.configure(fg=FG_HEAD if ghosting else FG_HEAD_ON_COLOUR)
            self.lbl_sub.configure(fg=FG_GHOST_SUB if ghosting else FG_DIM)
        else:
            if self.style == "bucket":
                self._draw_bucket(state.five_pct, colour)
            else:
                self._draw_pie(state.five_pct, colour)
            self.lbl_pct.configure(fg=colour)
            self.lbl_sub.configure(fg=FG_GHOST_SUB if ghosting else FG_DIM)

        self.lbl_pct.configure(text=pct_text)
        self.lbl_sub.configure(text=sub)

    def _tick(self):
        try:
            # Pick up changes made from the tray without a restart.
            cfg = core.load_config()
            if core.get_style(cfg) != self.style:
                self.set_style(core.get_style(cfg))
            elif core.get_ghost(cfg) != self.ghost:
                self.set_ghost(core.get_ghost(cfg))
            else:
                self.refresh()
        except Exception:
            pass  # A bad poll must never kill the overlay.
        self.root.after(POLL_MS, self._tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Overlay().run()
