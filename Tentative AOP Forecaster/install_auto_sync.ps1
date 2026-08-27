# Run once (right-click -> Run with PowerShell) to register a scheduled task
# that runs the full data-lake -> Postgres sync (sync/run_all.py) once a day.
#
# Why this exists: store_actuals_sync.py only ever pulls in a calendar month
# once the real date has moved past it (never a still-open, partial month) -
# and engine_v3.py's forecast engine independently refuses to use a
# not-yet-closed month's actuals even if one's already in the DB. Together
# that means a month's numbers appear in the dashboard automatically the
# first time this task runs after that month closes - no manual "Sync into
# database" click needed. Confirmed with the user 2026-08-27.

$taskName   = "RS Planning - Actuals Auto Sync"
$scriptPath = "$PSScriptRoot\run_auto_sync.ps1"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

# Once a day is enough - a month only ever transitions from "open" to
# "closed" once, at midnight on the 1st, so nothing is gained by checking
# more often. 05:00 gives the overnight batch on the data lake side time to
# settle before this reads it.
$trigger = New-ScheduledTaskTrigger -Daily -At "05:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "RS Planning - runs sync/run_all.py once a day so a newly-closed month's actuals sync in automatically." | Out-Null

Write-Host ""
Write-Host "  Task registered: $taskName" -ForegroundColor Green
Write-Host "  Runs daily at 05:00 - syncs Store Master, Store Actuals, day-shift calendar and the Calendar Engine reindex." -ForegroundColor Cyan
Write-Host "  Log: $PSScriptRoot\auto_sync.log" -ForegroundColor Gray
Write-Host ""
Write-Host "  Run it right now to test:  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Gray
Write-Host "  To uninstall:              .\uninstall_auto_sync.ps1" -ForegroundColor Gray
Write-Host ""
pause
