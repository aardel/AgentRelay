# Copy AgentRelay shortcut launcher to the Windows Desktop.
param(
    [string] $ProjectRoot = $PSScriptRoot + "\.."
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path $ProjectRoot).Path
$desktop = [Environment]::GetFolderPath("Desktop")
$dest = Join-Path $desktop "AgentRelay.cmd"

$content = @"
@echo off
setlocal
set "AGENTRELAY_ROOT=$root"
set "AGENTRELAY_CONFIG=$root\config.yaml"
call "$root\scripts\Launch-AgentRelay.cmd"
"@
Set-Content -LiteralPath $dest -Value $content -Encoding ASCII
Write-Host "Installed: $dest"
Write-Host "Double-click AgentRelay on your Desktop to start."
