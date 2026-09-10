@echo off
rem Learns from your usage history and Claude Code's transcripts, then prints
rem what past runs cost and whether one fits in what's left of your limits.
rem It already runs by itself in the background; this is for looking at it.
rem Local only: reads files on disk, no network, no tokens.
setlocal

rem Lives in windows\; the Python and the venv are one level up.
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "ROOT=%ROOT%\"
set "PY=%ROOT%.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERROR] venv not found at:
  echo   %PY%
  echo.
  echo Run setup.bat once ^(it sits next to this file^) and try again.
  echo.
  pause
  exit /b 1
)

"%PY%" "%ROOT%usage_learn.py"
echo.
pause
