# Run once (right-click -> Run with PowerShell) to register a scheduled task
# that health-checks the Sales Plan server every 3 minutes and auto-restarts
# it if it's down or hung. Complements install_service.ps1 (which starts the
# server at login and restarts it if the process exits) by also catching the
# case where the process is still alive but stopped responding.

$taskName    = "CityKart Sales Plan Watchdog"
$scriptPath  = "$PSScriptRoot\watchdog.ps1"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 3) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "CityKart Sales Plan - checks the server every 3 min and restarts it if hung or down." | Out-Null

Start-ScheduledTask -TaskName $taskName

Write-Host ""
Write-Host "  Task registered: $taskName" -ForegroundColor Green
Write-Host "  Checks http://localhost:8002 every 3 minutes; restarts on failure." -ForegroundColor Cyan
Write-Host "  Log: $PSScriptRoot\watchdog.log" -ForegroundColor Gray
Write-Host ""
Write-Host "  To stop:      Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor Gray
Write-Host "  To uninstall: .\uninstall_service.ps1  (removes both the server and watchdog tasks)" -ForegroundColor Gray
Write-Host ""
pause
