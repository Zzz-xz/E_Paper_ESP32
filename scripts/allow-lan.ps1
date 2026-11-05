#Requires -RunAsAdministrator
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$ruleName = "EPaper-LAN-TCP-$Port"
New-NetFirewallRule -Name $ruleName -DisplayName "E-Paper LAN TCP $Port" `
    -Direction Inbound -Action Allow -Enabled True -Profile Private `
    -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet | Out-Null
Write-Output "Allowed local subnet access to TCP $Port on private networks."
