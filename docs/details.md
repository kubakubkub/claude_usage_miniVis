# Details

The long version, for when the [README](../README.md) isn't enough.

## How it works

```
Claude Code ──stdin JSON──> statusline.py ──┬─> ~/.claude/usage-mirror.json ──┬─> tray.pyw
                                            │                                 └─> overlay.pyw
                                            ├─> ~/.claude/usage-history.jsonl
                                            ├─> one-line status in the Claude Code UI
                                            └─> starts usage_learn.py (at most every 30 min)

usage-history.jsonl + Claude Code transcripts ──> usage_learn.py ──> ~/.claude/usage-model.json
                                                                       ├─> overlay.pyw (run estimate)
                                                                       └─> the usage report
```

The pieces don't know about each other. The visualizers never talk to Claude
Code, the statusline doesn't know they exist, and the learner runs in the
background without holding up a render. You can restart any of them on its own,
and run the tray, the overlay, both, or neither.

The mirror only keeps what gets displayed: the rate limits, model name, context
percentage and Claude Code version. The full payload also has `session_id`,
`transcript_path`, `cwd` and `cost.total_cost_usd`. You don't need any of that
to draw a percentage, and the mirror is exactly the file you'd attach to a bug
report. Pass `--full` in the statusLine command if you want everything captured
for debugging.

Every open Claude Code session renders its own status line from its own last API
response. A session you just `/clear`ed, or one that hasn't made its first call
yet, sends no limits at all. An idle one sends its older, lower number. Neither
gets to overwrite the mirror: a window's number only moves up, or over to a new
window. The mirror also records when the limits were last actually reported, and
that's what "stale" is measured from.

### Usage history

Whenever a limit window rises or resets, `statusline.py` also adds one line to
`~/.claude/usage-history.jsonl`:

```
{"t":1789049709.9,"5h":23,"5h_reset":1789065600,"7d":12,"7d_reset":1789506000}
```

The mirror only holds the latest value. The history shows how fast the numbers
move, and it's what [the learner](#will-this-run-fit) and the [pace](#pace)
work from. Lower readings from idle sessions are dropped here too, or the history
would flicker between sessions.

Same rules as the mirror: timestamps and percentages, nothing about sessions,
paths or cost. The learner drops lines older than six weeks, and past 1 MB the
file rolls over to `usage-history.1.jsonl` as a backstop.

## Verified payload shape

Checked live against Claude Code **v2.1.220** and again on **v2.1.267**:

```
rate_limits.five_hour.used_percentage    e.g. 58
rate_limits.five_hour.resets_at          unix ts
rate_limits.seven_day.used_percentage    e.g. 59
rate_limits.seven_day.resets_at          unix ts
model.display_name                       e.g. "Opus 5 (1M context)"
context_window.used_percentage           e.g. 5
```

`rate_limits` is missing under API-key auth, and right after `/clear` until the
session's first API response. With no earlier numbers to fall back on, you get a
grey `--` and a tooltip saying why, not a made-up 0%.

## macOS notes

### Don't use Apple's system Python for the windows

`/usr/bin/python3` ships Tk 8.5.9, from 2010, and it can't draw widgets on a
current macOS. The window opens at the right size and place, says it's on
screen, and shows nothing at all, just an empty rectangle. I reproduced it on
macOS 26.5.2 with a plain `Frame` and `Label` in a normal decorated window. So
it isn't the overlay's frameless style, its window level or ghost mode. Tk just
doesn't paint.

That rules out the overlay, the chooser and the settings window. The tray icon
is fine on system Python because it never touches Tk: it draws with Pillow and
hands AppKit an `NSImage`. If the menu-bar icon works but the overlay is an empty
box, this is why.

Install a Python that comes with Tk 8.6 (the python.org macOS installer does,
and so does Homebrew's `python-tk`) and rebuild the venv with it:

```bash
rm -rf .venv
python3.13 -m venv .venv          # any python.org / brew 3.x with Tk 8.6
macos/claude-usage.sh setup
```

To check what you have:

```bash
python3 -c "import tkinter; r=tkinter.Tk(); print(r.tk.call('info','patchlevel'))"
```

`8.5.9` is the broken one. `setup` warns about it too.

### Always-on-top

Tk 8.5 on macOS doesn't implement `wm attributes -topmost`. It reports success
and does nothing, so the overlay ends up at the normal window level, where every
other window covers it. Everything else about it is right: it exists, it's at the
right coordinates, it's on screen, and you can't see it. `overlay.pyw` sets the
`NSWindow` level through AppKit instead. It does that a moment after startup,
because the level only sticks once the window is mapped, and again for the hover
tooltip, which is created later.

**Don't bring this back:** moving the window into the Aqua `floating` class with
`::tk::unsupported::MacWindowStyle` also reaches the floating level and looks
like a neater fix with no dependencies. But it quietly undoes
`overrideredirect`. The overlay comes back 24px taller, with a title bar and
traffic lights, and its content never draws.

**Menu-bar icon sharpness.** pystray sizes the icon in pixels to the menu bar's
thickness (22) and gives AppKit a 22×22 PNG. AppKit reads that as 22 points, so
on a Retina screen it gets stretched over 44 pixels and looks like a soft blob
next to the system icons. `tray.pyw` renders at the screen's scale factor and
declares the size in points, so it draws 1:1. The size was always right; this
only fixes the blur.

**Finding the processes.** Tkinter needs a windowed app bundle, so the
interpreter re-launches itself through the framework stub, and its command line
becomes `.../Python.app/Contents/MacOS/Python overlay.pyw`, with a capital P.
`claude-usage.sh` matches without caring about case. A case-sensitive match
reports a healthy process as failed and then leaves it running where `stop`
can't find it.

### Ghost mode

Windows only. Tk on macOS has no `-transparentcolor` at all. It raises
`bad attribute "-transparentcolor": must be -alpha, -fullscreen, -modified,
-notify, -titlepath, -topmost, or -transparent`, so the overlay catches that and
falls back to the normal dark panel, and the settings window tells you so.

## The overlay

A frameless widget with the 5-hour percentage, and the 7-day window and reset
times under it.

- Drag it anywhere. It remembers where you put it.
- Double-click to open the usage page.
- Hover for everything else: both windows with countdowns, the pace, the run
  estimate, when the numbers were last reported, and the model.
- The small arrow in the top-right corner folds it down to one line (label,
  percentage, and a ⚠ if the run estimate or the pace looks bad) and back out.
  The right edge stays where it is, so the arrow doesn't jump away from your
  mouse. It remembers whether it was folded.
- Right-click for: open usage page, style, estimate for, ghost mode, folded,
  appearance, reset position, quit.

### Pace

This uses the [usage history](#usage-history) to work out how fast the 5-hour
window has been filling over the last hour. If you'd hit 100% before the reset at
that rate, the overlay adds a line like `↗ full ~15:20`, and the tray tooltip says
so too. If you're fine, the widget stays quiet and the hover text says something
like `Pace +5%/h: lasts to reset`.

It only reports a pace while you're actually working: usage has to have gone up
in the last 15 minutes, by at least 2 points over at least 10 minutes. It's
worked out locally, so no tokens.

The tray tooltip also shows the run estimate for whatever the overlay is set to
estimate for. Windows cuts tray tooltips off at 127 characters, so when it's
full the least useful lines go first (the model, then the header).

### Run estimate

Once [the learner](#will-this-run-fit) has enough data, the overlay tells you
whether a run of the type picked under **right-click → Estimate for** (a Workflow
run, a reviewer agent, and so on) still fits:

- On the bucket and pie, a faint band above the fill shows where a typical run
  would take the 5-hour window, and a thin mark shows where a bad one would.
- In every style, one line under the reset times says `✓ workflow ~16% fits`
  (green), `⚠ workflow 16-47% tight` (amber) or `⚠ workflow: wait for 20:40`
  (red). Red means don't start a multi-agent job now.

The line disappears while the numbers are stale or before anything's been
learned, and **Off** hides it. The screenshots above are older than this line.

### Appearance

Right-click → **Appearance...** opens a few sliders:

| Control | Range | Effect |
|---------|-------|--------|
| Size | 60%–250% | scales fonts, graphic and padding together |
| Opacity | 25%–100% | whole-widget translucency |
| Ghost mode | on/off | removes the panel entirely |

Values are clamped both when read and when saved, so a hand-edited config can't
give you a 4000-pixel widget or an invisible one.

### Ghost mode

Ghost mode drops the background. Only the figure and the text float on the
desktop, and the drawing itself carries the colour:

- badge: no tile, the number itself is coloured
- bucket: unchanged, since it was always just an outline and a fill
- pie: the grey track ring goes, leaving only the used arc

Three things to know:

- **Windows only.** It works by making the colour `#010203` transparent with
  `-transparentcolor`, which Tk only supports on Windows. Elsewhere you get the
  normal dark panel, and the settings window tells you why.
- **Clicks go through the empty parts.** Grab the figure or the text to drag it.
  Clicks on empty space land on whatever is underneath.
- **Text has a faint dark edge.** That transparency is all-or-nothing per pixel,
  so the smoothed edges of letters, blended against the key colour, stay behind
  as a thin fringe. You can see it in the ghost screenshots. It comes with the
  technique and can't be tuned away.

The overlay stays out of the taskbar and Alt-Tab, and moves itself back on
screen if your display layout changes.

## Colours

The colour follows the 5-hour window on a smooth scale, so every percentage point
gets its own shade and 98% looks clearly darker than 90%. The anchor points are
`COLOR_STOPS` in `usage_core.py`:

| Usage | Colour | Hex |
|-------|--------|-----|
| 0% | green | `#2ea043` |
| 50% | amber | `#d29922` |
| 75% | orange | `#db6d28` |
| 90% | red | `#da3633` |
| 100% | dark red | `#7c1016` |
| stale | its colour, faded halfway to grey | e.g. 62% `#a2794a` |
| unknown | grey | `#6e6e6e` |

Everything in between is blended: 93% is `#c72e2d`, 95% `#ab2324`, 98%
`#8f181c`. Change `COLOR_STOPS` to reshape it; the tray and the overlay both
follow.

Stale means no session has reported limits for 10 minutes. The last numbers stay
up, faded, with an `as of 25m ago` line. I'd rather show an old number that's
probably right than an empty widget, and the fade is enough to tell you it's
old. Run estimates are hidden while stale.

## Reset times

The overlay and the tray show the reset as a clock time, so you don't have to do
the maths, with the countdown next to it:

```
   61%
5h  14:10  (1h 33m)
7d  60%  Tue 23:00
```

The format depends on how far off it is: `14:10` today, `Tue 23:00` this week,
`03 Aug 12:34` after that.

> `resets_at` is when the *current* window rolls over, not "now plus the window
> length". A 7-day window with 82h left is normal; it started about 3.6 days ago.

## Will this run fit?

Before a review or a long Workflow run, double-click `windows\usage-report.bat`,
or `macos/Usage-Report.command` on a Mac (`macos/claude-usage.sh report` in a
terminal):

```
1% of each limit is about:
  5-hour  $1.24   from 14% seen in 1 window, low confidence
  7-day   $16.7   from 14% seen in 1 window, low confidence

Finished runs                      count   typical    worst   5h worst   7d worst
  workflow                             14     $19.3    $58.4        47%       3.5%
    release-review                      3     $19.0    $58.4
  agent: reviewer                      22     $3.21    $13.2        11%       0.8%

Right now: 5h 39% (resets 20:40), 7d 14% (resets Tue 23:00)
  workflow        5h fits (typical 16%, worst 47%, 61% left); 7d fits (typical 1.2%, worst 3.5%, 86% left)
  agent: reviewer 5h fits (typical 2.6%, worst 11%, 61% left); 7d fits (typical 0.2%, worst 0.8%, 86% left)
```

The overlay shows the same verdict in one line; see [Run estimate](#run-estimate).

Running it costs nothing. `usage_learn.py` reads the usage history and Claude
Code's own session transcripts from your disk and does arithmetic. No Claude
calls, no network, no tokens.

How it gets there:

- **What a run cost is exact.** Every response in `~/.claude/projects` records
  its tokens and model. A Workflow run's agents are stored together, and
  subagents started by other subagents count toward the run above them.
- **What 1% is has to be learned.** Anthropic doesn't publish how tokens turn
  into percent, so the learner watches the history and, whenever a window
  rises, adds up what was spent in that stretch. The `$` is just a common scale:
  tokens at Claude API list prices, so output, cache reads and different models
  can be compared. It isn't a bill.
- **Typical** is the median run and **worst** the 90th percentile. `fits` means
  even a bad run fits in what's left, `tight` means a typical one fits but a bad
  one wouldn't, and `likely cut off` means even a typical one doesn't.

You don't have to run it to keep it current. `statusline.py` starts it in the
background at most every 30 minutes, without waiting for it, and it writes
`~/.claude/usage-model.json`. Measurements stay there for six weeks, so they
outlive Claude Code deleting transcripts after 30 days.

Some caveats:

- It starts out rough. The 5-hour rate needs several windows before it says
  `ok confidence`, and the 7-day rate a few weeks. Until then, treat it as a
  ballpark.
- It only sees this machine. Usage on claude.ai, your phone or another computer
  counts toward your limits but leaves no transcripts here, which makes runs look
  cheaper than they are. The report shows any rise it couldn't explain.
- A run costs what you point it at. Reviewing a big diff costs more than a small
  one. The gap between typical and worst is the honest answer to "how much?".
- The 7-day window is assumed to start at 0% seven days before its reset. That
  matched real snapshots taken four weeks apart. The 5-hour window didn't pass
  the same check, so it's only measured between two readings.
- `usage-model.json` contains Workflow names and project folder names. Unlike
  the mirror, don't attach it to a public bug report.
- I've only verified the history and the learner on Windows. They're plain
  Python with nothing platform-specific, but they haven't run on macOS or Linux
  yet.

## Files

Shared, in the repo root. This is the actual program, one copy for both
platforms:

| File | Purpose |
|------|---------|
| `statusline.py` | Claude Code statusLine: mirrors payload, logs history, starts the learner |
| `usage_learn.py` | Learns rates and run costs from history + transcripts; prints the report |
| `check_private.py` | Privacy check: blocks pushing keys, emails, local paths, private terms |
| `.githooks/pre-push` | Runs that check on every push, once enabled |
| `CLAUDE.md` | Rules for Claude Code working in this repo, privacy first |
| `usage_core.py` | Shared reading/formatting/colour/style/pace logic |
| `usage_tk.py` | Shared Tk canvas drawing (overlay + chooser previews) |
| `tray.pyw` | Tray / menu-bar icon (pystray + Pillow) |
| `overlay.pyw` | Floating desktop widget (Tkinter only) |
| `chooser.pyw` | Preset picker with live previews (Tkinter only) |
| `install_statusline.py` | Safe settings.json editor (backup + atomic write) |
| `probe_statusline.py` | Re-verify the payload shape after a Claude Code upgrade |

The launchers are thin, and they're the only files that differ per platform:

| File | Purpose |
|------|---------|
| `windows\setup.bat` | Create the venv + install deps |
| `windows\install-statusline.bat` | Wrapper for `install_statusline.py` |
| `windows\choose.bat` | Double-click to open the chooser |
| `windows\start/stop-*.bat` | Start/stop the tray and overlay |
| `windows\make-startup-shortcut.ps1` | Creates/removes the Startup shortcut |
| `windows\usage-report.bat` | Double-click for the usage report |
| `macos/claude-usage.sh` | The real macOS/Linux launcher for everything |
| `macos/*.command` | Double-clickable Finder wrappers (tray, statusline, report) |

## If the schema changes after an upgrade

Point `statusLine.command` at `probe_statusline.py` and let it capture a few
renders into `probe-dump.jsonl`. Look through it, then re-run the installer
(`windows\install-statusline.bat` or `macos/Install-Statusline.command`) to
switch back. The probe only writes that dump.

## Security

- **There's nothing to connect to from outside.** No server, no open port, no
  network calls.
- **Text from transcripts stays text.** Transcripts can contain text from
  anywhere: repositories, web pages, agent descriptions. The learner only parses
  them as JSON and adds up numbers, and names on the overlay are plain labels.
  Nothing from them is run, used as a command, or turned into a file path.
- **Code in this folder runs automatically, so guard it.** Claude Code runs
  `statusline.py` on every render, which starts `usage_learn.py` in the
  background, and the pre-push hook runs on every push. Anyone who can change
  files here, or a malicious change you pull or merge, gets code running as you.
  Read diffs before pulling, and don't install from a fork you haven't looked at.
- **Local data files.** `~/.claude/usage-model.json` names your Workflow runs and
  project folders. Only programs running as you can read it, and those could
  read the transcripts it comes from anyway.

## Notes

- No file here reads or sets `ANTHROPIC_API_KEY`. Setting it would switch Claude
  Code to paid API billing and remove `rate_limits` entirely.
- `statusline.py` can't break the status line. Every failure ends in a plain
  string, and it never prints a traceback.
- The mirror, model and settings are written atomically (temp file +
  `os.replace`), so nothing ever reads or leaves a half-written file.
- `statusline.py` never waits for the learner. It starts it detached, sharing no
  console or output, so a render takes as long as it always did.
- On Windows, one running visualizer shows up as two `pythonw.exe` processes.
  That's normal: the venv's `pythonw.exe` is a small stub that runs the real
  interpreter as a child. You still get one icon.
