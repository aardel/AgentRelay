# Build AgentRelay.exe for Windows (requires: pip install pyinstaller)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    python -m venv .venv
}
& $py -m pip install -q -r requirements.txt pyinstaller

& $py -m PyInstaller --noconfirm --windowed --name AgentRelay `
  --hidden-import aiohttp `
  --hidden-import zeroconf `
  --hidden-import yaml `
  --hidden-import pyperclip `
  --collect-submodules aiohttp `
  --collect-submodules zeroconf `
  (Join-Path $Root "agentrelay_app.py")

Write-Host ""
Write-Host "Built: $Root\dist\AgentRelay\AgentRelay.exe"
