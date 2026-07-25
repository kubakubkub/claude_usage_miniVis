"""Pick how claude_usage_miniVis looks, then start it.

Shows all three presets side by side -- drawn with the same code the live
widget uses, and with your real current usage -- plus the ghost, size and
opacity controls. Choosing applies immediately, so anything already running
updates while you look at it.

  Windows:  pythonw.exe chooser.pyw     (or double-click choose.bat)
  macOS:    python3 chooser.pyw         (or ./claude-usage.sh choose)

Put this in Startup instead of the overlay if you'd rather pick a look each
session than have one restored.

Standard library only. No network calls, no credentials, no API key.
"""
import os
import subprocess
import sys
import webbrowser

try:
    import tkinter as tk
except Exception:  # pragma: no cover - Tk missing
    sys.stderr.write("tkinter is required. On Debian/Ubuntu: sudo apt install python3-tk\n")
    raise SystemExit(1)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import usage_core as core
import usage_tk as utk

PREVIEW = 78
PANEL_BG = "#26262a"
SEL_BG = "#3a3a41"
SEL_RING = "#7aa2f7"
FG = "#f0f0f3"
FG_DIM = "#9a9aa2"

FONT = "Segoe UI" if sys.platform.startswith("win") else \
       ("Helvetica Neue" if sys.platform == "darwin" else "DejaVu Sans")

# CREATE_NO_WINDOW -- launch the .bat without flashing a console.
_NO_WINDOW = 0x08000000


class Chooser:
    def __init__(self):
        self.cfg = core.load_config()
        self.style = core.get_style(self.cfg)

        self.root = tk.Tk()
        self.root.title("Claude usage - choose a look")
        self.root.configure(bg=PANEL_BG, padx=16, pady=14)
        self.root.resizable(False, False)

        self._tiles = {}
        self._build()
        self.refresh()
        self.root.after(5000, self._tick)

    # ---------- layout ----------

    def _build(self):
        tk.Label(self.root, text="Choose a look", bg=PANEL_BG, fg=FG,
                 font=(FONT, 13, "bold")).pack(anchor="w")
        self.lbl_state = tk.Label(self.root, text="", bg=PANEL_BG, fg=FG_DIM,
                                  font=(FONT, 8), justify="left")
        self.lbl_state.pack(anchor="w", pady=(0, 10))

        row = tk.Frame(self.root, bg=PANEL_BG)
        row.pack()
        for s in core.STYLES:
            tile = tk.Frame(row, bg=PANEL_BG, padx=8, pady=8,
                            highlightthickness=2, highlightbackground=PANEL_BG)
            tile.pack(side="left", padx=5)
            canvas = tk.Canvas(tile, width=PREVIEW, height=PREVIEW, bg=PANEL_BG,
                               highlightthickness=0, bd=0)
            canvas.pack()
            label = tk.Label(tile, text=core.STYLE_LABELS[s].split(" (")[0],
                             bg=PANEL_BG, fg=FG_DIM, font=(FONT, 8))
            label.pack(pady=(5, 0))
            for w in (tile, canvas, label):
                w.bind("<Button-1>", lambda e, s=s: self.pick(s))
            self._tiles[s] = (tile, canvas, label)

        opts = tk.Frame(self.root, bg=PANEL_BG)
        opts.pack(fill="x", pady=(14, 0))

        self.ghost_var = tk.BooleanVar(value=core.get_ghost(self.cfg))
        tk.Checkbutton(opts, text="Ghost mode (no background)", variable=self.ghost_var,
                       bg=PANEL_BG, fg=FG, selectcolor=PANEL_BG, activebackground=PANEL_BG,
                       activeforeground=FG, highlightthickness=0, anchor="w",
                       font=(FONT, 9), command=self.on_ghost).pack(fill="x")

        self._slider(opts, "Size", int(core.SCALE_MIN * 100), int(core.SCALE_MAX * 100),
                     int(round(core.get_scale(self.cfg) * 100)), self.on_size)
        self._slider(opts, "Opacity", int(core.ALPHA_MIN * 100), 100,
                     int(round(core.get_alpha(self.cfg) * 100)), self.on_alpha)

        btns = tk.Frame(self.root, bg=PANEL_BG)
        btns.pack(fill="x", pady=(14, 0))
        tk.Button(btns, text="Start overlay", command=lambda: self.launch("overlay"),
                  font=(FONT, 9)).pack(side="left")
        tk.Button(btns, text="Start tray", command=lambda: self.launch("tray"),
                  font=(FONT, 9)).pack(side="left", padx=6)
        tk.Button(btns, text="Usage page", command=self.open_usage,
                  font=(FONT, 9)).pack(side="left")
        tk.Button(btns, text="Close", command=self.root.destroy,
                  font=(FONT, 9)).pack(side="right")

        self.lbl_msg = tk.Label(self.root, text="", bg=PANEL_BG, fg=FG_DIM,
                                font=(FONT, 8), justify="left", wraplength=330)
        self.lbl_msg.pack(anchor="w", pady=(8, 0))

    def _slider(self, parent, text, lo, hi, value, cmd):
        tk.Label(parent, text=text, bg=PANEL_BG, fg=FG, anchor="w",
                 font=(FONT, 9)).pack(fill="x", pady=(8, 0))
        s = tk.Scale(parent, from_=lo, to=hi, orient="horizontal", resolution=5,
                     bg=PANEL_BG, fg=FG, troughcolor="#1c1c1f", highlightthickness=0,
                     activebackground=SEL_RING, font=(FONT, 7), command=cmd)
        s.set(value)
        s.pack(fill="x")
        return s

    # ---------- actions ----------

    def pick(self, style):
        self.style = core.set_style(style)
        self.cfg = core.load_config()
        self.refresh(force=True)

    def on_ghost(self):
        core.set_ghost(self.ghost_var.get())
        self.cfg = core.load_config()
        self.refresh(force=True)

    def on_size(self, value):
        core.set_scale(float(value) / 100.0)
        self.cfg = core.load_config()

    def on_alpha(self, value):
        core.set_alpha(float(value) / 100.0)
        self.cfg = core.load_config()

    def open_usage(self):
        try:
            webbrowser.open(core.USAGE_URL)
        except Exception:
            pass

    def launch(self, component):
        """Start a visualizer via the existing launcher, which already refuses
        to start a second copy."""
        try:
            if os.name == "nt":
                script = os.path.join(ROOT, "start-%s.bat" % component)
                if not os.path.exists(script):
                    self.lbl_msg.configure(text="Missing %s" % os.path.basename(script))
                    return
                subprocess.Popen(["cmd", "/c", script], cwd=ROOT,
                                 creationflags=_NO_WINDOW, close_fds=True)
            else:
                script = os.path.join(ROOT, "claude-usage.sh")
                if not os.path.exists(script):
                    self.lbl_msg.configure(text="Missing claude-usage.sh")
                    return
                subprocess.Popen(["bash", script, component], cwd=ROOT, close_fds=True)
            self.lbl_msg.configure(
                text="Starting %s... (it won't start twice if already running)" % component)
        except Exception as exc:
            self.lbl_msg.configure(text="Could not start %s: %s" % (component, exc))

    # ---------- rendering ----------

    def refresh(self, force=False):
        state = core.read_state()
        colour = core.to_hex(core.pick_color(state.five_pct, state.stale))
        ghost = core.get_ghost(self.cfg)
        pct = state.five_pct

        if state.has_limits:
            self.lbl_state.configure(
                text="Now: 5h %d%%  resets %s     7d %s%%" % (
                    state.five_pct or 0, core.fmt_clock(state.five_reset),
                    state.seven_pct if state.seven_pct is not None else "--"))
        else:
            self.lbl_state.configure(text=state.problem or "no usage data yet")

        for s, (tile, canvas, label) in self._tiles.items():
            bg = SEL_BG if s == self.style else PANEL_BG
            tile.configure(bg=bg, highlightbackground=SEL_RING if s == self.style else PANEL_BG)
            canvas.configure(bg=bg)
            label.configure(bg=bg, fg=FG if s == self.style else FG_DIM)

            if s == "badge":
                utk.draw_badge(canvas, PREVIEW, pct, colour, ghost,
                               font=(FONT, int(PREVIEW * 0.30), "bold"))
            elif s == "bucket":
                utk.draw_bucket(canvas, PREVIEW, pct, colour)
            else:
                utk.draw_pie(canvas, PREVIEW, pct, colour, hole_bg=bg,
                             show_track=not ghost)

    def _tick(self):
        try:
            # Stay in step with the tray and overlay menus, which write the same
            # config. Sliders are left alone so a live drag isn't fought.
            self.cfg = core.load_config()
            self.style = core.get_style(self.cfg)
            self.ghost_var.set(core.get_ghost(self.cfg))
            self.refresh()
        except Exception:
            pass  # A bad poll must never kill the chooser.
        self.root.after(5000, self._tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Chooser().run()
