# Run ONCE as Administrator (right-click → Run with PowerShell)
# Adds a permanent Windows Firewall rule so port 8002 is always reachable on the LAN.

$ruleName = "CityKart Sales Plan 8002"

# Remove stale rule if it exists
netsh advfirewall firewall delete rule name="$ruleName" | Out-Null

# Add inbound TCP rule for port 8002
netsh advfirewall firewall add rule `
    name="$ruleName" `
    dir=in `
    action=allow `
    protocol=TCP `
    localport=8002 `
    profile=private,domain `
    description="CityKart Sales Plan — allows LAN access to the FastAPI server on port 8002."

Write-Host ""
Write-Host "  Firewall rule added: $ruleName" -ForegroundColor Green
Write-Host ""
Write-Host "  Access the app from any device on this network:" -ForegroundColor White
Write-Host "    http://CKHO-L-A9820:8002" -ForegroundColor Yellow
Write-Host ""
Write-Host "  This URL is permanent — it uses the machine hostname, not the IP," -ForegroundColor Cyan
Write-Host "  so it works even after DHCP reassigns a new IP address."           -ForegroundColor Cyan
Write-Host ""
pause
