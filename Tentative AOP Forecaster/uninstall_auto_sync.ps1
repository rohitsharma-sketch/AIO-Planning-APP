# Removes the daily auto-sync task registered by install_auto_sync.ps1.
$taskName = "RS Planning - Actuals Auto Sync"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "  Removed: $taskName" -ForegroundColor Green
pause
