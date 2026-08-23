# Run this once to create the Sales Plan desktop icon.
# Right-click → Run with PowerShell

$batPath     = "$PSScriptRoot\start.bat"
$iconSrc     = "$PSScriptRoot\icon.ico"
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcut    = Join-Path $desktopPath "Sales Plan.lnk"

$wsh  = New-Object -ComObject WScript.Shell
$link = $wsh.CreateShortcut($shortcut)
$link.TargetPath       = $batPath
$link.WorkingDirectory = $PSScriptRoot
$link.Description      = "CityKart Sales Plan — opens at http://localhost:8002"
$link.WindowStyle      = 7   # minimised — servers run quietly in tray

# Use custom icon if present, otherwise fall back to a built-in Windows one
if (Test-Path $iconSrc) {
    $link.IconLocation = "$iconSrc,0"
} else {
    $link.IconLocation = "%SystemRoot%\System32\shell32.dll,135"
}

$link.Save()

Write-Host ""
Write-Host "  Desktop shortcut created: Sales Plan"  -ForegroundColor Green
Write-Host "  Double-click it any time to launch."   -ForegroundColor Cyan
Write-Host ""
