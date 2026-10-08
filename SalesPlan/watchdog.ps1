# Health-checks the Sales Plan server on port 8002 and restarts it if it's
# down OR hung (process alive but not answering — the failure mode a plain
# "restart on crash" task doesn't catch). Meant to run on a repeating
# scheduled task; see install_watchdog.ps1.

$port       = 8002
$url        = "http://localhost:$port/api/store-master"
$backendDir = "$PSScriptRoot\backend"
$py         = "C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$logFile    = "$PSScriptRoot\watchdog.log"

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg"
    Add-Content -Path $logFile -Value $line
    # Keep the log from growing forever
    $lines = Get-Content -Path $logFile -ErrorAction SilentlyContinue
    if ($lines.Count -gt 1000) {
        Set-Content -Path $logFile -Value ($lines | Select-Object -Last 500)
    }
}

$healthy = $false
try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -eq 200) { $healthy = $true }
} catch {}

if ($healthy) { exit 0 }

Write-Log "UNHEALTHY - restarting server"

# Kill only processes belonging to this app (identified by command line),
# not unrelated python/uvicorn processes elsewhere on the machine.
Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'uvicorn.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'main:app' } |
    ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
            Write-Log "  killed stale PID $($_.ProcessId)"
        } catch {}
    }

Start-Sleep -Seconds 1

Start-Process -FilePath $py `
    -ArgumentList "-m uvicorn main:app --host 127.0.0.1 --port $port" `
    -WorkingDirectory $backendDir `
    -WindowStyle Hidden

# Confirm it actually came back up
$recovered = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $recovered = $true; break }
    } catch {}
}

if ($recovered) {
    Write-Log "  recovered, server responding again"
} else {
    Write-Log "  FAILED to recover after restart attempt"
}
