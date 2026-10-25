<#
 MConn receiver: Windows setup (UNVERIFIED on a real machine; part of the Phase 0 spike).
 Run in an elevated PowerShell from windows-receiver\:   .\scripts\install_windows.ps1
 - Adds an inbound firewall rule scoped to the Private profile (+ Domain), LocalSubnet and Tailscale (100.64.0.0/10)
 - Registers a Task Scheduler job that starts the receiver at user logon
#>
param(
  [int]$Port = 8443,
  [string]$Python = (Get-Command python).Source
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# Install into the receiver's own environment. The scheduled task must not
# depend on whichever Python happens to be first on PATH at logon.
$venv = Join-Path $root ".venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
  & $Python -m venv $venv
}
$venvPython = Join-Path $venv "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e $root

# 1. Firewall: never open the receiver to Public networks or the internet.
Remove-NetFirewallRule -DisplayName "MConn Receiver" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "MConn Receiver" -Direction Inbound -Protocol TCP -LocalPort $Port `
  -Action Allow -Profile Private,Domain -RemoteAddress LocalSubnet,100.64.0.0/10 | Out-Null

# 2. Scheduled task at logon (runs as the current user, no console window via pythonw if present)
$exe = Join-Path $venv "Scripts\pythonw.exe"
if (-not (Test-Path $exe)) { $exe = $venvPython }
$action  = New-ScheduledTaskAction -Execute $exe -Argument "-m mconn_receiver" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "MConn Receiver" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Installed. Start now with:  Start-ScheduledTask -TaskName 'MConn Receiver'"
Write-Host "Pair a phone at:            https://127.0.0.1:$Port/admin"
