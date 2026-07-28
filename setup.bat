@echo off
rem One-time setup: creates .venv next to this file and installs dependencies.
rem Double-click it, or run:  setup.bat
rem Safe to re-run -- an existing venv is reused and its deps just refreshed.
setlocal

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "PY=%VENV%\Scripts\python.exe"

echo === claude_usage_miniVis setup ===
echo Folder: %ROOT%
echo.

if exist "%PY%" (
  echo Found an existing venv - refreshing its dependencies.
  goto :deps
)

call :find_python
if not defined BOOT goto :no_python

echo Creating venv with: %BOOT%
%BOOT% -m venv "%VENV%"
if errorlevel 1 goto :venv_failed
if not exist "%PY%" goto :venv_failed

:deps
echo.
echo Installing dependencies...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 (
  echo.
  echo [ERROR] pip install failed - see the output above.
  echo         Only the tray icon needs these packages; the overlay,
  echo         chooser and statusline run on the standard library alone.
  echo.
  pause
  exit /b 1
)

rem Tkinter is standard library, but slimmed-down Python builds sometimes drop
rem it -- and every window in this project is Tkinter. Better to say so now
rem than to have start-overlay.bat fail silently with no console to print to.
"%PY%" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [WARN] This Python has no tkinter, so the overlay, chooser and tray
  echo        windows cannot open. Reinstall Python from python.org with the
  echo        "tcl/tk and IDLE" option ticked, delete .venv, then re-run this.
)

echo.
echo Setup complete.
echo.
echo Next, double-click any of these:
echo   install-statusline.bat   wire the statusline into Claude Code
echo   choose.bat               preview the presets, then start one
echo   start-overlay.bat        floating desktop badge
echo   start-tray.bat           tray icon
echo.
pause
exit /b 0


:find_python
rem "py -3" first: on a fresh Windows, plain "python" is often the Microsoft
rem Store alias stub, which opens the Store instead of running anything.
set "BOOT="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "BOOT=py -3"
if defined BOOT exit /b 0
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "BOOT=python"
exit /b 0


:no_python
echo [ERROR] No Python 3.8 or newer found on PATH.
echo.
echo Install it from https://www.python.org/downloads/windows/ and tick
echo "Add python.exe to PATH" in the installer, then run this again.
echo.
echo If Python is installed but "python" opens the Microsoft Store instead,
echo turn off the alias: Settings ^> Apps ^> Advanced app settings ^>
echo App execution aliases ^> switch off python.exe and python3.exe.
echo.
pause
exit /b 1


:venv_failed
echo.
echo [ERROR] Could not create the venv at:
echo   %VENV%
echo.
echo Common causes: no write permission in this folder, or a half-created
echo .venv left over from an interrupted run - delete it and try again.
echo.
pause
exit /b 1
