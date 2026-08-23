# Run once (right-click → Run with PowerShell) to register the Sales Plan
# server as a startup task.  After that: server starts automatically at login
# and is reachable at http://<your-ip>:8002 from any browser on the LAN.

$taskName    = "CityKart Sales Plan Server"
$pythonExe   = "C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\Scripts\uvicorn.exe"
$backendDir  = "$PSScriptRoot\backend"
$args        = "main:app --host 0.0.0.0 --port 8002"

# Validate paths
if (-not (Test-Path $pythonExe)) {
    # Fallback: find uvicorn next to python.exe
    $pythonExe = "C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    $args      = "-m uvicorn main:app --host 0.0.0.0 --port 8002"
    if (-not (Test-Path $pythonExe)) {
        Write-Host "  ERROR: Python not found. Check the path in this script." -ForegroundColor Red
        pause; exit 1
    }
}

# Remove stale task if it exists
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction -Execute $pythonExe -Argument $args -WorkingDirectory $backendDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

# Run hidden (no console window)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "CityKart Sales Plan — auto-starts FastAPI server on port 8002 at login." | Out-Null

# Start it right now too
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2

# Add firewall rule if running as admin (silently skip if not)
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")
if ($isAdmin) {
    netsh advfirewall firewall delete rule name="CityKart Sales Plan 8002" | Out-Null
    netsh advfirewall firewall add rule name="CityKart Sales Plan 8002" dir=in action=allow protocol=TCP localport=8002 profile=private,domain description="CityKart Sales Plan LAN access" | Out-Null
    Write-Host "  Firewall rule: added" -ForegroundColor Green
} else {
    Write-Host "  Firewall rule: run install_firewall.ps1 as Administrator to allow LAN access" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Task registered: $taskName" -ForegroundColor Green
Write-Host "  Server starts automatically at every login."   -ForegroundColor Cyan
Write-Host ""
Write-Host "  Open from any device on this network (permanent URL):" -ForegroundColor White
Write-Host "    http://CKHO-L-A9820:8002"                            -ForegroundColor Yellow
Write-Host ""
Write-Host "  To stop:      Stop-ScheduledTask  -TaskName '$taskName'"   -ForegroundColor Gray
Write-Host "  To uninstall: .\uninstall_service.ps1"                      -ForegroundColor Gray
Write-Host ""
pause
