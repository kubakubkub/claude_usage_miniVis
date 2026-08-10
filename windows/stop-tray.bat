@echo off
rem Stops the Claude usage tray. Same as right-click -> Quit on the icon,
rem but works if the icon is unresponsive or hidden in the overflow area.
setlocal

rem One tray = a venv redirector stub plus its child interpreter. Kill the
rem whole set, tolerating pids that die as a side effect of their parent.
powershell -NoProfile -Command "$p = @(Get-CimInstance Win32_Process -Filter ('Name=' + [char]39 + 'pythonw.exe' + [char]39) -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*tray.pyw*' }); if ($p.Count -eq 0) { Write-Host 'Claude usage tray is not running.'; exit 0 }; $ids = @($p | ForEach-Object { $_.ProcessId }); $roots = @($p | Where-Object { $ids -notcontains $_.ParentProcessId }); $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Host ('Stopped ' + $roots.Count + ' tray instance(s).')"

ping -n 3 127.0.0.1 >nul 2>&1
exit /b 0
