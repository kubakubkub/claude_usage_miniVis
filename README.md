# claude_usage_miniVis

**Am I about to hit my limit?** A glanceable answer, without typing a command.

![presets](screenshots/presets.png)

Shows the **real** numbers — the `rate_limits` Claude Code already sends to your
status line, the same figures your account reports. No token-cost estimation, no
API key, no credentials, no scraping, no network calls of any kind. It reads one
local file and draws a percentage. Zero tokens.

Small on purpose. This is not a dashboard: it answers "is it worth kicking off
this big refactor now, or should I wait for the reset?" and nothing else. The
detail lives in your terminal status line; this is the ambient version.

- **`tray.pyw`** — system-tray / menu-bar icon
- **`overlay.pyw`** — always-on-top badge floating on the desktop
- **`chooser.pyw`** — preview the presets, then start either one

## Status

| | |
|---|---|
| Claude Code | verified against **v2.1.220** |
| Windows 11 | developed and tested |
| macOS 26, Apple silicon | statusline + tray **verified**; overlay/chooser Windows-only in practice |
| Linux | **written, not yet verified** |
| Python | 3.12 tested. On macOS **do not use system Python** — see below |

The statusLine payload is not a documented, stable API. If a Claude Code upgrade
renames a field this degrades to `--` rather than breaking; re-verify with
`probe_statusline.py` and open an issue.

macOS was first run end-to-end on 2026-08-10. The statusline and the menu-bar
icon work and are the supported macOS surface. The **overlay badge and chooser
are Windows features in practice**: they are Tk windows, and the Tk 8.5.9 in
Apple's `/usr/bin/python3` cannot draw widgets on a current macOS at all — see
[macOS notes](#macos-notes). Linux support is real code —
path handling, the launcher script, the Tk fallbacks — but has not been run
there yet. Ghost mode is Windows-only by design (see below). Reports and PRs
welcome.

## Requires Claude Code

**Install [Claude Code](https://claude.com/claude-code) first, and sign in with a
Pro or Max subscription.** This tool has no data of its own — it only mirrors
what Claude Code hands to its status line, so there is nothing to show until
Claude Code is installed, authenticated and has run at least once.

On an API-key login there are no `rate_limits` at all (that billing has no
subscription windows), and the visualizers will sit at a grey `--`. Same right
after `/clear`, until the session's first response.

**This cannot work for claude.ai in a browser alone.** The only data source is
Claude Code piping JSON into a statusLine command on your machine. With no
Claude Code, there is no local file to mirror — and reading usage out of the
website would mean lifting session cookies or hitting claude.ai with your
credentials. That's deliberately out of scope.

The web UI is still fine as the *display* target — the menu item opens
claude.ai/settings/usage — but the *numbers* come from Claude Code.

## How it works

```
Claude Code ──stdin JSON──> statusline.py ──> ~/.claude/usage-mirror.json ──┬─> tray.pyw
                                 │                                          └─> overlay.pyw
                                 └──> one-line status in the Claude Code UI
```

Fully decoupled: the visualizers never talk to Claude Code, and the statusline
never knows they exist. Any piece can be restarted independently, and you can
run the tray, the overlay, both, or neither.

The mirror stores **only** what gets displayed — the rate limits, model name,
context percentage and Claude Code version. The full payload also carries
`session_id`, `transcript_path`, `cwd` and `cost.total_cost_usd`; none of that
is needed to draw a percentage, and the mirror is exactly the file you'd attach
to a bug report. Pass `--full` in the statusLine command if you want everything
captured for debugging.

## Verified payload shape

Confirmed live against Claude Code **v2.1.220** (not assumed):

```
rate_limits.five_hour.used_percentage    e.g. 58
rate_limits.five_hour.resets_at          unix ts
rate_limits.seven_day.used_percentage    e.g. 59
rate_limits.seven_day.resets_at          unix ts
model.display_name                       e.g. "Opus 5 (1M context)"
context_window.used_percentage           e.g. 5
```

`rate_limits` is **absent** under API-key auth, and absent right after `/clear`
until the session's first API response. Both cases show a grey `--` with an
explanatory tooltip rather than a misleading 0%.

## Install

**Prerequisites:** [Claude Code](https://claude.com/claude-code) installed and
signed in on a Pro/Max subscription, and Python 3. That's it — no account to
create here, no key to paste anywhere.

Launchers are split by platform: **everything you double-click for Windows is in
`windows\`, and everything for macOS is in `macos\`**. The Python itself is
shared and stays in the repo root, along with the single `.venv` both sides use
— so there is exactly one copy of the actual program, and picking the wrong
folder is impossible rather than merely discouraged.

```
claude_usage_miniVis/
  statusline.py  overlay.pyw  tray.pyw  chooser.pyw  usage_*.py   <- shared
  windows/   setup.bat, start/stop-*.bat, make-startup-shortcut.ps1
  macos/     Setup.command, Start-Tray.command, ... + claude-usage.sh
```

### Windows

```powershell
git clone https://github.com/kubakubkub/claude_usage_miniVis.git
cd claude_usage_miniVis
```

Then double-click **`windows\setup.bat`** — it creates `.venv` and installs the
dependencies. It's safe to re-run: an existing venv is reused and its packages
just refreshed. If Python isn't on PATH, or `python` opens the Microsoft Store
instead of running, it says exactly what to fix.

Prefer the command line? `python -m venv .venv` then
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt` does the same
thing.

Next, double-click **`windows\install-statusline.bat`** — it backs up
`settings.json` with a timestamp and writes only the `statusLine` key. No
hand-editing, no jq.

```
install-statusline.bat              install
install-statusline.bat --uninstall  remove the statusLine key
install-statusline.bat --show       print the current setting
install-statusline.bat --force      replace another statusLine without asking
```

Restart Claude Code afterwards.

**Already running a statusLine?** (ccstatusline or similar.) The installer will
show it and ask before replacing — it never overwrites someone else's setup
silently. A timestamped backup is written either way, and `--uninstall` only
removes the key; restoring your previous one means copying it back from that
backup.

### macOS

On macOS you get the **statusline**, the **menu-bar icon** and the terminal
`status` readout. The draggable overlay badge and the chooser are effectively
**Windows-only** — they are Tk windows, and Tk cannot draw on Apple's system
Python (see [macOS notes](#macos-notes)). Nothing here needs them.

Open the **`macos`** folder and double-click, in this order:

| Double-click | Does |
|---|---|
| `Setup.command` | create the venv + install deps (once, after cloning) |
| `Install-Statusline.command` | wire the statusline into Claude Code |
| `Start-Tray.command` | menu-bar icon |
| `Status.command` | what's running + the current numbers |
| `Stop.command` | stop the tray |

They exist because Finder will not run a bare `.sh` — each is a two-line wrapper
around `claude-usage.sh`, which remains the real launcher and is what you want
from a terminal:

```bash
macos/claude-usage.sh setup      # venv + deps
macos/claude-usage.sh install    # wire up settings.json (backs up first)
macos/claude-usage.sh tray       # menu-bar icon
macos/claude-usage.sh status     # what's running + current numbers
macos/claude-usage.sh stop
```

`overlay` and `choose` still exist as subcommands and work on a Python with **Tk
8.6**, but they get no `.command` file — a double-click that reliably opens an
empty window is worse than no double-click at all.

Restart Claude Code after `install`. The first time you double-click a
`.command`, Gatekeeper may ask you to confirm — right-click → Open once, and it
stops asking.

### Linux

Use `macos/claude-usage.sh` — the script itself is POSIX shell and platform-neutral
despite the folder name; only the `.command` wrappers beside it are Mac-specific.
Written but not yet verified on Linux.

```bash
macos/claude-usage.sh setup
macos/claude-usage.sh install
macos/claude-usage.sh overlay
```

The overlay needs only Tkinter (standard library). On Debian/Ubuntu that's
`sudo apt install python3-tk`. The tray additionally needs pystray + Pillow,
and PyObjC on macOS — all handled by `setup`.

Exec bits are committed, so no `chmod` is needed unless your checkout lost them
(`chmod +x macos/*.command macos/claude-usage.sh`).

## macOS notes

### Do not use Apple's system Python for the windows

**`/usr/bin/python3` ships Tk 8.5.9 — released in 2010 — and it cannot draw
widgets on a current macOS.** The window opens at the right size and position,
reports itself on-screen, and renders *nothing*: no background, no text, an
empty rectangle. Confirmed on macOS 26.5.2 with a plain `Frame` + `Label` in a
normal, undecorated window, so it is not the overlay's frameless styling, its
window level, or ghost mode — Tk simply does not paint.

That kills the **overlay**, the **chooser** and the settings window. The **tray
icon is unaffected** and works fine on system Python, because it never uses Tk:
it draws with Pillow and hands AppKit an `NSImage`. So "menu-bar icon fine, but
the badge is an empty window" is the signature of exactly this problem.

Install a Python that bundles **Tk 8.6** — the python.org macOS installer does,
Homebrew's `python-tk` does — and rebuild the venv with it:

```bash
rm -rf .venv
python3.13 -m venv .venv          # any python.org / brew 3.x with Tk 8.6
macos/claude-usage.sh setup
```

Check what you have with:

```bash
python3 -c "import tkinter; r=tkinter.Tk(); print(r.tk.call('info','patchlevel'))"
```

`8.5.9` is the broken one. `setup` warns about it too.

### Always-on-top

Tk 8.5's Aqua port does not implement `wm attributes -topmost`: it reports
success and does nothing, leaving the overlay at the normal window layer where
every ordinary window covers it — created correctly, right coordinates,
on-screen, and buried. `overlay.pyw` sets the `NSWindow` level directly through
AppKit instead, deferred via `after()` because it only sticks once the window
has been mapped.

**Rejected alternative, do not reintroduce:** promoting the window to the Aqua
`floating` class with `::tk::unsupported::MacWindowStyle` also reaches the
floating layer and looks like the tidier, dependency-free fix. It silently
undoes `overrideredirect` — the badge comes back 24px taller with a full title
bar and traffic lights, and its content never renders.

**Menu-bar icon resolution.** pystray sizes the status-item image in pixels to
the menu bar thickness (22) and hands AppKit a 22×22 PNG, which AppKit reads as
22 *points* — so on a Retina display it is stretched across 44 device pixels
from a 22-pixel source, and reads as a soft blob beside the crisp system icons.
`tray.pyw` backs the image at the screen's scale factor and declares its size in
points, so it draws 1:1. It is the right size either way; only the sharpness
changes.

**Process detection.** Tkinter needs a windowed app bundle, so the interpreter
re-execs through the framework stub and its command line becomes
`.../Python.app/Contents/MacOS/Python overlay.pyw` — every "python" capitalised.
`claude-usage.sh` matches case-insensitively; a case-sensitive match reports a
perfectly healthy process as failed and then orphans it where `stop` cannot see
it.

### Ghost mode

Windows-only. Aqua Tk has no `-transparentcolor` at all — it raises
`bad attribute "-transparentcolor": must be -alpha, -fullscreen, -modified,
-notify, -titlepath, -topmost, or -transparent` — so the overlay catches that
and falls back to the normal dark panel, as the settings window says.

## Run (Windows)

Everything here lives in the **`windows`** folder.

| Double-click | Does |
|---|---|
| `setup.bat` | create the venv + install deps (once, after cloning) |
| `choose.bat` | preview the presets, then start one |
| `start-tray.bat` | tray icon |
| `stop-tray.bat` | stop it |
| `start-overlay.bat` | floating desktop badge |
| `stop-overlay.bat` | stop it |

The launchers refuse to double-start, and point you at `setup.bat` if the venv
is missing. They resolve the venv and the `.pyw` files one level up, so they
work double-clicked from Explorer regardless of the current directory — but
they do expect to stay inside `windows\`.

### Start at login

Not installed automatically — run it yourself:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\make-startup-shortcut.ps1            # tray
powershell -ExecutionPolicy Bypass -File .\windows\make-startup-shortcut.ps1 -Overlay   # overlay
```

Undo with `-Remove`, or delete the `.lnk` from `shell:startup` (Win+R).

The shortcut points at `pythonw.exe` directly, so nothing flashes on screen.
The `.bat` files briefly show a console; the shortcut doesn't.

## What it looks like

![presets](screenshots/presets.png)

Three presets, each in normal and ghost mode. All six are real captures at the
same moment, so the numbers match across them.

Tray icons across the range — the colour is a continuous ramp, not fixed bands:

![tray icons](screenshots/tray-icons.png)

## The chooser

![chooser](screenshots/chooser.png)

Double-click **`windows\choose.bat`** to preview all three presets side by side,
drawn with the same code the live widget uses and with your real current usage.
(Windows only in practice — it is a Tk window, see [macOS notes](#macos-notes).) Picking one applies immediately, so anything
already running updates while you watch.

From there you can start the overlay or the tray directly — it goes through the
normal launchers, so it still won't start a second copy.

Put **`chooser.pyw`** in Startup instead of a visualizer if you'd rather pick a
look each session than have one restored:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\make-startup-shortcut.ps1 -Chooser
```

## Three presets

Pick from the **right-click menu → Style**, on either the tray icon or the
overlay, or from the chooser. The choice is shared — all of them switch
together, live, no restart — and saved to `~/.claude/usage-visualizer.json`.

| Preset | Looks like |
|--------|-----------|
| `badge` | flat tile, percentage as a big number |
| `bucket` | tapered pail that fills up as usage climbs |
| `pie` | round donut dial sweeping clockwise from 12 o'clock |

Every preset is labelled **CLAUDE USAGE** on the overlay — a filling bucket next
to a clock reads as a battery indicator otherwise.

Note the trade-off in the *tray*: `badge` is the only preset showing a readable
number at 16×16. `bucket` and `pie` convey the fraction by shape instead; the
exact number is in the tooltip.

## The overlay

A frameless widget showing the 5-hour percentage, with the 7-day window and
reset times underneath.

- **Drag** it anywhere — the position is saved
- **Double-click** opens the usage page
- **Right-click** for: open usage page, style, ghost mode, appearance, reset
  position, quit

### Appearance

Right-click → **Appearance...** opens sliders:

| Control | Range | Effect |
|---------|-------|--------|
| Size | 60%–250% | scales fonts, graphic and padding together |
| Opacity | 25%–100% | whole-widget translucency |
| Ghost mode | on/off | removes the panel entirely |

Values are clamped on read as well as write, so a hand-edited config can't
produce a 4000-pixel widget or an invisible one.

### Ghost mode

Drops the background completely — only the figure and text float on the
desktop, with the usage colour carried by the drawing itself:

- **badge** — no tile; the number itself takes the colour
- **bucket** — unchanged (it was always just an outline plus its fill level)
- **pie** — the grey track ring disappears, leaving only the used arc

Two caveats worth knowing:

- **Windows only.** It works by chroma-keying `#010203` to transparent via
  `-transparentcolor`, which Tk only supports on Windows. Elsewhere it falls
  back to the normal dark panel and the settings window says so.
- **Transparent pixels are click-through.** Grab the figure or the text to drag
  it; empty space passes clicks to whatever is underneath.
- **Text picks up a faint dark halo.** Colour-key transparency is all-or-nothing
  per pixel, so anti-aliased glyph edges — blended against the key colour —
  stay put as a thin fringe. Visible in the ghost screenshots above. Inherent to
  the technique, not a bug that can be tuned out.

It stays out of the taskbar and the Alt-Tab list, and clamps itself back on
screen if your display layout changes.

## Colours

A **continuous** ramp driven by the 5-hour window — every percentage point gets
its own shade, so 98% reads visibly darker than 90% rather than both flattening
to the same red. Anchor points (`COLOR_STOPS` in `usage_core.py`):

| Usage | Colour | Hex |
|-------|--------|-----|
| 0% | green | `#2ea043` |
| 50% | amber | `#d29922` |
| 75% | orange | `#db6d28` |
| 90% | red | `#da3633` |
| 100% | dark red | `#7c1016` |
| stale / unknown | grey | `#6e6e6e` |

Everything between is interpolated: 93% `#c72e2d`, 95% `#ab2324`, 98% `#8f181c`.
Edit `COLOR_STOPS` to reshape the ramp; both visualizers follow it.

"Stale" = the mirror file is older than 10 minutes, i.e. Claude Code hasn't
rendered a status line recently. The last known numbers stay visible, greyed
and marked `STALE`, rather than vanishing.

## Reset times

Both show the wall-clock reset time so you don't do the arithmetic, with the
countdown alongside:

```
   61%
5h  14:10  (1h 33m)
7d  60%  Tue 23:00
```

Format adapts to distance: `14:10` today, `Tue 23:00` within the week,
`03 Aug 12:34` beyond that.

> `resets_at` is when the *current* window rolls over, not "now plus the window
> length." A 7-day window sitting at 82h left is normal — it started ~3.6 days
> ago.

## Files

Shared, in the repo root — the actual program, one copy for both platforms:

| File | Purpose |
|------|---------|
| `statusline.py` | Claude Code statusLine: mirrors payload, prints status line |
| `usage_core.py` | Shared reading/formatting/colour/style logic |
| `usage_tk.py` | Shared Tk canvas drawing (overlay + chooser previews) |
| `tray.pyw` | Tray / menu-bar icon (pystray + Pillow) |
| `overlay.pyw` | Floating desktop badge (Tkinter only) |
| `chooser.pyw` | Preset picker with live previews (Tkinter only) |
| `install_statusline.py` | Safe settings.json editor (backup + atomic write) |
| `probe_statusline.py` | Re-verify the payload shape after a Claude Code upgrade |

Platform launchers — thin, and the only files that differ per OS:

| File | Purpose |
|------|---------|
| `windows\setup.bat` | Create the venv + install deps |
| `windows\install-statusline.bat` | Wrapper for `install_statusline.py` |
| `windows\choose.bat` | Double-click to open the chooser |
| `windows\start/stop-*.bat` | Start/stop the tray and overlay |
| `windows\make-startup-shortcut.ps1` | Creates/removes the Startup shortcut |
| `macos/claude-usage.sh` | The real macOS/Linux launcher for everything |
| `macos/*.command` | Double-clickable Finder wrappers (tray + statusline only) |

## If the schema changes after an upgrade

Point `statusLine.command` at `probe_statusline.py`, let it capture a few
renders into `probe-dump.jsonl`, inspect it, then re-run the installer
(`windows\install-statusline.bat` or `macos/Install-Statusline.command`)
to switch back. The probe writes a dump and nothing else.

## Notes

- `ANTHROPIC_API_KEY` is never read or set by any file here. Setting it would
  reroute Claude Code to paid API billing and blank out `rate_limits` entirely.
- `statusline.py` cannot crash the status line: every failure path degrades to
  a plain string, and a traceback is never printed to stdout.
- Mirror and settings writes are atomic (temp file + `os.replace`), so nothing
  can read or leave a half-written file.
- On Windows, one running visualizer shows as **two** `pythonw.exe` processes.
  That's normal — the venv's `pythonw.exe` is a redirector stub that runs the
  base interpreter as a child. There's still only one icon.
