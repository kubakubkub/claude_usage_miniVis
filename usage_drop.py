"""Start Claude Code in a folder from the overlay. Windows only.

Two ways in: drop a folder on the widget, or pick one of the recent project
folders from the right-click menu (recent_projects below).

Dropping:

Tk has no drag-and-drop of its own. Windows can still hand dropped files to any
window that asks for them (DragAcceptFiles): it posts WM_DROPFILES with a
handle listing the paths. So we subclass the overlay's top-level window
procedure with ctypes, pick that one message out, and pass everything else on
to Tk untouched. Standard library only, like the rest of the overlay.

The window procedure must not touch Tk. It runs inside Tk's message dispatch,
while Tkinter has released the GIL; calling root.after() from there kills the
process ("PyEval_RestoreThread: the function must be called with the GIL
held"). So it only reads the paths into a list, and a short Tk timer picks
them up and does the launch.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

WM_DROPFILES = 0x0233
WM_COPYDATA = 0x004A
WM_COPYGLOBALDATA = 0x0049
GWLP_WNDPROC = -4
MSGFLT_ALLOW = 1

POLL_MS = 250

# Kept alive for the life of the process: if the ctypes callback were garbage
# collected, Windows would call into freed memory on the next message.
_hooks = []


def enable(root, on_drop):
    """Make `root` accept dropped files; call on_drop(list_of_paths) on a drop.

    Returns True if it's active. Never raises: anywhere it can't work (not
    Windows, an unexpected Tk build) the overlay just behaves as before.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)

        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.CallWindowProcW.restype = LRESULT
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                           wintypes.WPARAM, wintypes.LPARAM]
        shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
        shell32.DragQueryFileW.restype = wintypes.UINT
        shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                           wintypes.LPWSTR, wintypes.UINT]
        shell32.DragFinish.argtypes = [wintypes.HANDLE]

        root.update_idletasks()
        # The real top-level window. For a frameless (overrideredirect) Tk
        # window, winfo_id() is an inner child; wm_frame() is the outer one.
        hwnd = int(root.wm_frame(), 16)

        old_proc = None
        pending = []

        def proc(h, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                paths = []
                try:
                    hdrop = wparam
                    count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                    for i in range(count):
                        n = shell32.DragQueryFileW(hdrop, i, None, 0)
                        buf = ctypes.create_unicode_buffer(n + 1)
                        shell32.DragQueryFileW(hdrop, i, buf, n + 1)
                        paths.append(buf.value)
                finally:
                    shell32.DragFinish(wparam)
                if paths:
                    pending.append(paths)  # plain Python only; see the docstring
                return 0
            return user32.CallWindowProcW(old_proc, h, msg, wparam, lparam)

        callback = WNDPROC(proc)
        old_proc = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC,
                                            ctypes.cast(callback, ctypes.c_void_p))
        if not old_proc:
            return False
        _hooks.append((callback, old_proc))

        # Lets a drop from a non-elevated Explorer through even if the overlay
        # happens to run elevated. Harmless when it doesn't.
        try:
            for m in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
                user32.ChangeWindowMessageFilterEx(hwnd, m, MSGFLT_ALLOW, None)
        except Exception:
            pass
        shell32.DragAcceptFiles(hwnd, True)

        def poll():
            while pending:
                try:
                    on_drop(pending.pop(0))
                except Exception:
                    pass
            root.after(POLL_MS, poll)

        root.after(POLL_MS, poll)
        return True
    except Exception:
        return False


def folder_for(paths):
    """The folder to start in: the first dropped folder, or the folder that
    holds the first dropped file. None if nothing usable was dropped."""
    for p in paths:
        if os.path.isdir(p):
            return p
    for p in paths:
        parent = os.path.dirname(p)
        if parent and os.path.isdir(parent):
            return parent
    return None


def find_shell():
    """PowerShell 7 if installed, else the Windows PowerShell every Windows has."""
    return shutil.which("pwsh") or shutil.which("powershell")


def launch_claude(folder):
    """Open a new PowerShell window in `folder` running `claude`.

    The folder goes in as the working directory, never into the command text,
    so no path can be misread as PowerShell. -NoExit keeps the window open
    after claude exits, or if it isn't on PATH, so any error stays readable.
    Raises OSError / RuntimeError if it can't start; the caller reports it.
    """
    shell = find_shell()
    if not shell:
        raise RuntimeError("PowerShell not found on PATH.")
    subprocess.Popen([shell, "-NoLogo", "-NoExit", "-Command", "claude"],
                     cwd=folder, env=clean_env(),
                     creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)


def _persistent_env_names():
    """Upper-cased names of the variables set in the user's and the machine's
    environment (the ones you set in Windows settings), as opposed to ones
    some parent process added on the way down."""
    names = set()
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                          (winreg.HKEY_LOCAL_MACHINE,
                           r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    i = 0
                    while True:
                        try:
                            names.add(winreg.EnumValue(k, i)[0].upper())
                        except OSError:
                            break
                        i += 1
            except OSError:
                pass
    except ImportError:
        pass
    return names


def clean_env():
    """This process's environment minus Claude Code's session markers.

    If the overlay was started from inside a Claude Code session (say, a
    session that restarted it), it inherits that session's CLAUDECODE,
    CLAUDE_PID, CLAUDE_CODE_* and similar variables. A claude started with
    those thinks it is a child of that session: it doesn't save its
    transcript, and starts without the project's memory or earlier sessions.
    So every CLAUDE* variable is dropped -- except the ones you set yourself
    in the Windows environment, which are your settings, not markers.
    """
    keep = _persistent_env_names()
    env = {}
    for name, value in os.environ.items():
        up = name.upper()
        if up.startswith("CLAUDE") and up not in keep:
            continue
        env[name] = value
    return env


RECENT_SHOWN = 10
CWD_LINES = 50  # the cwd is on one of the first lines of a transcript


def _cwd_of(transcript):
    """The working directory a transcript was started in, or None."""
    try:
        with open(transcript, "r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= CWD_LINES:
                    break
                if '"cwd"' not in line:
                    continue
                try:
                    cwd = json.loads(line).get("cwd")
                except (ValueError, AttributeError):
                    continue
                if isinstance(cwd, str) and cwd:
                    return cwd
    except OSError:
        pass
    return None


def recent_projects(claude_dir, limit=RECENT_SHOWN):
    """Folders you recently ran Claude Code in, newest first.

    Read from ~/.claude/projects on demand and never stored. Claude Code keeps
    one folder of transcripts per project, but the folder name is a lossy
    encoding of the path, so the path comes from the newest transcript's
    "cwd" field instead. Folders that no longer exist are left out.
    """
    newest = []
    for project in glob.glob(os.path.join(claude_dir, "projects", "*")):
        best = None
        for path in glob.glob(os.path.join(project, "*.jsonl")):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, path)
        if best:
            newest.append(best)
    newest.sort(reverse=True)

    out, seen = [], set()
    for _mtime, path in newest:
        cwd = _cwd_of(path)
        if not cwd:
            continue
        key = os.path.normcase(os.path.normpath(cwd))
        if key in seen or not os.path.isdir(cwd):
            continue
        seen.add(key)
        out.append(os.path.normpath(cwd))
        if len(out) >= limit:
            break
    return out


def menu_label(folder):
    """'name   (parent)' -- the name first, so the list scans quickly."""
    folder = os.path.normpath(folder)
    name = os.path.basename(folder) or folder
    parent = os.path.dirname(folder)
    return "%s   (%s)" % (name, parent) if parent and parent != folder else name
