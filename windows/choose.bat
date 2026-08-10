@echo off
rem Opens the visual chooser: preview all three presets, set ghost/size/opacity,
rem and start the overlay or tray from there. No console window.
setlocal

rem Lives in windows\; the Python and the venv are one level up.
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "ROOT=%ROOT%\"
set "PYW=%ROOT%.venv\Scripts\pythonw.exe"
set "APP=%ROOT%chooser.pyw"

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
  echo [ERROR] chooser.pyw not found at:
  echo   %APP%
  pause
  exit /b 1
)

powershell -NoProfile -Command "if (@(Get-CimInstance Win32_Process -Filter ('Name=' + [char]39 + 'pythonw.exe' + [char]39) -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*chooser.pyw*' }).Count -gt 0) { exit 1 }"
if errorlevel 1 (
  echo Chooser is already open - nothing to do.
  ping -n 3 127.0.0.1 >nul 2>&1
  exit /b 0
)

start "" "%PYW%" "%APP%"
exit /b 0
