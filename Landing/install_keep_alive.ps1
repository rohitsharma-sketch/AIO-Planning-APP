# One-time: registers "RS Planning - Keep Alive" for the current user (no admin needed). It runs keep_alive.py at
# sign-in and every 2 minutes; keep_alive.py starts Landing (7800) when it is down, and Landing restarts the rest.
# Right-click -> Run with PowerShell (or: powershell -ExecutionPolicy Bypass -File install_keep_alive.ps1)
$py   = "C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
$name = "RS Planning - Keep Alive"
$act  = New-ScheduledTaskAction -Execute $py -Argument "keep_alive.py" -WorkingDirectory $PSScriptRoot
$logon  = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$set  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
$who  = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $act -Trigger $logon, $repeat -Settings $set -Principal $who -Force | Out-Null
Write-Host "Registered '$name' - Landing is checked at sign-in and every 2 minutes." -ForegroundColor Green
Start-ScheduledTask -TaskName $name
