# Removes the auto-start and watchdog tasks and stops the server if running.
$taskName     = "CityKart Sales Plan Server"
$watchdogName = "CityKart Sales Plan Watchdog"

Stop-ScheduledTask  -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Stop-ScheduledTask  -TaskName $watchdogName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $watchdogName -Confirm:$false -ErrorAction SilentlyContinue

# Kill any process still holding port 8002
$pids = (netstat -ano | Select-String ":8002 ") -replace '.*\s+(\d+)$','$1' | Select-Object -Unique
foreach ($p in $pids) {
    try { Stop-Process -Id ([int]$p) -Force -ErrorAction Stop } catch {}
}

Write-Host ""
Write-Host "  Uninstalled: $taskName" -ForegroundColor Yellow
Write-Host "  Uninstalled: $watchdogName" -ForegroundColor Yellow
Write-Host "  Server stopped. Run install_service.ps1 / install_watchdog.ps1 to re-register." -ForegroundColor Gray
Write-Host ""
pause
