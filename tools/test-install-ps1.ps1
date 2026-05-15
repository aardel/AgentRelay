$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$installer = Join-Path $root "install.ps1"

function Assert-Contains {
    param(
        [string] $Text,
        [string] $Pattern,
        [string] $Message
    )

    if ($Text -notmatch $Pattern) {
        throw $Message
    }
}

if (-not (Test-Path -LiteralPath $installer)) {
    throw "install.ps1 is missing"
}

$content = Get-Content -LiteralPath $installer -Raw

Assert-Contains $content "param\s*\(" "install.ps1 must define script parameters"
Assert-Contains $content "\`$Prefix\s*=" "install.ps1 must expose a Prefix parameter"
Assert-Contains $content "\`$Service" "install.ps1 must expose a Service switch"
Assert-Contains $content "python.+-m.+venv" "install.ps1 must create a Python virtual environment"
Assert-Contains $content "pip.+install.+requirements\.txt" "install.ps1 must install requirements.txt"
Assert-Contains $content "agentrelay\.cmd" "install.ps1 must create an agentrelay.cmd wrapper"
Assert-Contains $content "agent-send\.cmd" "install.ps1 must create an agent-send.cmd wrapper"
Assert-Contains $content "--init" "install.ps1 must initialize config if missing"
Assert-Contains $content "Get-Command\s+nssm" "install.ps1 must gate service installation on NSSM"
Assert-Contains $content "nssm.+install" "install.ps1 must install a service when NSSM is present"
Assert-Contains $content "nssm.+start" "install.ps1 must start the service when NSSM is present"
Assert-Contains $content "function\s+Invoke-Checked" "install.ps1 must check native command exit codes"
Assert-Contains $content "Invoke-Checked\s+\S+\s+@\(.*pip.*install" "install.ps1 must run pip through Invoke-Checked"
if ($content -match "--upgrade""?,\s*""?pip") {
    throw "install.ps1 must not self-upgrade pip during Windows installs"
}

Write-Host "install.ps1 contract checks passed"
