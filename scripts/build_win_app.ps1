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
  --add-data "$(Join-Path $Root 'gui');gui" `
  --hidden-import aiohttp `
  --hidden-import zeroconf `
  --hidden-import yaml `
  --hidden-import pyperclip `
  --hidden-import webview `
  --collect-submodules aiohttp `
  --collect-submodules zeroconf `
  (Join-Path $Root "agentrelay_gui.py")

Write-Host ""
Write-Host "Built: $Root\dist\AgentRelay\AgentRelay.exe"
