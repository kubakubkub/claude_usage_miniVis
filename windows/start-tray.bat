@echo off
rem Starts the Claude usage tray with no console window.
rem Double-click this, or point a Startup shortcut at it.
setlocal

rem Lives in windows\; the Python and the venv are one level up.
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "ROOT=%ROOT%\"
set "PYW=%ROOT%.venv\Scripts\pythonw.exe"
set "APP=%ROOT%tray.pyw"

if not exist "%PYW%" (
  echo [ERROR] venv not found at:
  echo   %PYW%
  echo.
  echo Run setup.bat once ^(it sits next to this file^) and try again.
  echo.
  pause
  exit /b 1
)

if not exist "%APP%" (
  echo [ERROR] tray.pyw not found at:
  echo   %APP%
  pause
  exit /b 1
)

rem Don't stack a second icon in the tray if it's already running.
rem Note: one running tray shows up as TWO pythonw processes -- the venv's
rem pythonw.exe is a redirector stub that runs the base interpreter as a child.
rem Any match at all means it's up, so a simple existence check is correct here.
powershell -NoProfile -Command "if (@(Get-CimInstance Win32_Process -Filter ('Name=' + [char]39 + 'pythonw.exe' + [char]39) -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*tray.pyw*' }).Count -gt 0) { exit 1 }"
if errorlevel 1 (
  echo Claude usage tray is already running - nothing to do.
  rem 'timeout' dies when stdin is redirected; ping is the portable delay.
  ping -n 3 127.0.0.1 >nul 2>&1
  exit /b 0
)

start "" "%PYW%" "%APP%"
exit /b 0
