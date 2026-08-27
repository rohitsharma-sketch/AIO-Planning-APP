# Run this once to make the Landing page start automatically at Windows
# login, so it's always reachable at http://localhost:7800 the moment a
# saved Chrome bookmark/shortcut for it is clicked - Landing is the "master
# switch" that launches every other app (see landing_server.py's /api/launch-
# all), so unlike those apps it can't just be brought up on demand by
# clicking something served from it; it has to already be running.
# Right-click -> Run with PowerShell

$batPath  = "$PSScriptRoot\start.bat"
$startup  = [Environment]::GetFolderPath("Startup")
$shortcut = Join-Path $startup "RS Planning Landing.lnk"

$wsh  = New-Object -ComObject WScript.Shell
$link = $wsh.CreateShortcut($shortcut)
$link.TargetPath       = $batPath
$link.WorkingDirectory = $PSScriptRoot
$link.Description      = "RS Planning Landing - auto-starts at login, serves http://localhost:7800"
$link.WindowStyle      = 7   # minimised - runs quietly, no console window in the way

$link.Save()

Write-Host ""
Write-Host "  Landing will now start automatically at login." -ForegroundColor Green
Write-Host "  Starting it now for this session too..."         -ForegroundColor Cyan
Write-Host ""

Start-Process -FilePath $batPath -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
