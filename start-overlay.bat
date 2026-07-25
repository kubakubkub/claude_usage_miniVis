@echo off
rem Starts the always-on-top desktop overlay badge (no console window).
setlocal

set "ROOT=%~dp0"
set "PYW=%ROOT%.venv\Scripts\pythonw.exe"
set "APP=%ROOT%overlay.pyw"

if not exist "%PYW%" (
  echo [ERROR] venv not found at:
  echo   %PYW%
  echo.
  echo Create it with:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

if not exist "%APP%" (
  echo [ERROR] overlay.pyw not found at:
  echo   %APP%
  pause
  exit /b 1
)

powershell -NoProfile -Command "if (@(Get-CimInstance Win32_Process -Filter ('Name=' + [char]39 + 'pythonw.exe' + [char]39) -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*overlay.pyw*' }).Count -gt 0) { exit 1 }"
if errorlevel 1 (
  echo Overlay is already running - nothing to do.
  ping -n 3 127.0.0.1 >nul 2>&1
  exit /b 0
)

start "" "%PYW%" "%APP%"
exit /b 0
