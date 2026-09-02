# Run the QA suite in a visible new terminal window.
# The browser opens on screen so you can watch each test live.
# Close that window when you're done, or let it finish on its own.

$qaDir = $PSScriptRoot

# Check auth state exists
if (-not (Test-Path "$qaDir\auth\state.json")) {
    Write-Host ""
    Write-Host "No auth session found. Run setup first:" -ForegroundColor Yellow
    Write-Host "  cd qa-runner && npm run setup" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

Write-Host "Starting QA run..." -ForegroundColor Green
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$qaDir'; Write-Host 'RS Planning QA Runner' -ForegroundColor Cyan; Write-Host ''; npx playwright test --reporter=list; Write-Host ''; Write-Host 'Done. Press Ctrl+C or close this window.' -ForegroundColor Green"
) -WindowStyle Normal
