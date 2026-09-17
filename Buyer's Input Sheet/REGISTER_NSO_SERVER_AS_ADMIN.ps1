# Right-click this file → "Run with PowerShell" (UAC will prompt for admin)
# OR open an Admin PowerShell and run: .\REGISTER_NSO_SERVER_AS_ADMIN.ps1

$vbs = "C:\Users\A9820\Documents\CLaude - New Projects\Buyer's Input Sheet\start_nso_server.vbs"

$action    = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`""
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User "CITYKR\a9820"
$settings  = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 2)
$principal = New-ScheduledTaskPrincipal `
    -UserId "CITYKR\a9820" `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName "NSO Distributor Server" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Starts NSO Plan Distributor Flask server on port 8060 at logon. Accessible at http://10.0.1.131:8060" `
    -Force

Write-Host ""
Write-Host "NSO Distributor Server task registered. It will auto-start on next logon."
Write-Host "To start it NOW without logging off: Start-ScheduledTask -TaskName 'NSO Distributor Server'"
Write-Host ""
Write-Host "Press Enter to close."
Read-Host
