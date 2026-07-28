# Creates a Startup shortcut so the tray launches at login.
# NOT run automatically -- run it yourself when you want it installed:
#   powershell -ExecutionPolicy Bypass -File .\make-startup-shortcut.ps1
#
# To undo: delete the .lnk from the folder printed at the end, or run with -Remove

# -Overlay  floating desktop badge instead of the tray icon
# -Chooser  show the preset picker at login instead of starting a visualizer
param([switch]$Remove, [switch]$Overlay, [switch]$Chooser)

$ErrorActionPreference = 'Stop'

$root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw  = Join-Path $root '.venv\Scripts\pythonw.exe'
if ($Chooser)      { $name = 'chooser.pyw'; $label = 'Claude Usage Chooser' }
elseif ($Overlay)  { $name = 'overlay.pyw'; $label = 'Claude Usage Overlay' }
else               { $name = 'tray.pyw';    $label = 'Claude Usage Tray' }
$script   = Join-Path $root $name
$startup  = [Environment]::GetFolderPath('Startup')
$lnk      = Join-Path $startup "$label.lnk"

if ($Remove) {
    if (Test-Path $lnk) { Remove-Item $lnk -Force; "Removed: $lnk" }
    else { "Nothing to remove at: $lnk" }
    return
}

if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found at $pythonw -- run setup.bat first." }
if (-not (Test-Path $script))  { throw "$name not found at $script" }

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath       = $pythonw
$sc.Arguments        = "`"$script`""
$sc.WorkingDirectory = $root
$sc.WindowStyle      = 7            # minimized; pythonw shows nothing anyway
$sc.Description      = "$label - Claude subscription usage indicator"
$sc.Save()

"Created: $lnk"
"  target : $pythonw"
"  args   : `"$script`""
"Starts automatically at next login. Launch now with:"
"  Start-Process `"$pythonw`" -ArgumentList `"$script`""
