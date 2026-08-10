@echo off
rem Wires statusline.py into Claude Code's settings.json. Backs up first.
rem Run with:  install-statusline.bat            (install)
rem            install-statusline.bat --uninstall (remove)
setlocal

rem Lives in windows\; the Python and the venv are one level up.
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "ROOT=%ROOT%\"
set "PY=%ROOT%.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [WARN] venv not found ^(run setup.bat^), falling back to system python.
  set "PY=python"
)

"%PY%" "%ROOT%install_statusline.py" %*

echo.
pause
