@echo off
rem Wires statusline.py into Claude Code's settings.json. Backs up first.
rem Run with:  install-statusline.bat            (install)
rem            install-statusline.bat --uninstall (remove)
setlocal

set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [WARN] venv not found, falling back to system python.
  set "PY=python"
)

"%PY%" "%ROOT%install_statusline.py" %*

echo.
pause
