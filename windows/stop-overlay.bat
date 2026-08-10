@echo off
rem Stops the desktop overlay.
setlocal

powershell -NoProfile -Command "$p = @(Get-CimInstance Win32_Process -Filter ('Name=' + [char]39 + 'pythonw.exe' + [char]39) -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*overlay.pyw*' }); if ($p.Count -eq 0) { Write-Host 'Overlay is not running.'; exit 0 }; $ids = @($p | ForEach-Object { $_.ProcessId }); $roots = @($p | Where-Object { $ids -notcontains $_.ParentProcessId }); $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Host ('Stopped ' + $roots.Count + ' overlay instance(s).')"

ping -n 3 127.0.0.1 >nul 2>&1
exit /b 0
