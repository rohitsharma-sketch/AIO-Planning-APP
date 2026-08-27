# Runs sync/run_all.py and appends its output to auto_sync.log with a
# timestamp header. Meant to run on a daily scheduled task - see
# install_auto_sync.ps1. Not interactive: safe to run unattended.

$backendDir = $PSScriptRoot
$py         = "C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$logFile    = "$PSScriptRoot\auto_sync.log"

Add-Content -Path $logFile -Value "--- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ---" -Encoding utf8

Push-Location $backendDir
try {
    # Capture as PowerShell strings (Out-String) then write with an explicit
    # encoding, rather than `*>> $logFile` directly - that raw stream
    # redirect garbled every line into one-space-per-character mush the
    # first time this ran (a UTF-16/UTF-8 mismatch between PowerShell's
    # redirect and the python subprocess's own stdout encoding).
    $output = & $py "sync\run_all.py" 2>&1 | Out-String
    Add-Content -Path $logFile -Value $output -Encoding utf8
    Add-Content -Path $logFile -Value "exit code: $LASTEXITCODE" -Encoding utf8
} finally {
    Pop-Location
}

# Keep the log from growing forever
$lines = Get-Content -Path $logFile -ErrorAction SilentlyContinue
if ($lines.Count -gt 2000) {
    Set-Content -Path $logFile -Value ($lines | Select-Object -Last 1000)
}
