[CmdletBinding()]
param(
    [string] $Prefix = (Join-Path $env:LOCALAPPDATA "agentrelay"),
    [string] $Python = "",
    [switch] $Service,
    [string] $ServiceName = "agentrelay",
    [switch] $Force
)

$ErrorActionPreference = "Stop"

function Resolve-AgentRelayPython {
    param(
        [string] $RequestedPython,
        [string] $SourceDir
    )

    $candidates = @()
    if ($RequestedPython) {
        $candidates += $RequestedPython
    }
    if ($env:PYTHON) {
        $candidates += $env:PYTHON
    }
    $localPython = Join-Path $SourceDir ".python\python.exe"
    if (Test-Path -LiteralPath $localPython) {
        $candidates += $localPython
    }
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidates += $pythonCommand.Source
    }
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        $candidates += $pyCommand.Source
    }

    foreach ($candidate in $candidates) {
        try {
            $versionText = & $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            $parts = $versionText.Trim().Split(".")
            if ([int] $parts[0] -gt 3 -or ([int] $parts[0] -eq 3 -and [int] $parts[1] -ge 10)) {
                return $candidate
            }
        } catch {
            continue
        }
    }

    throw "Python 3.10 or newer was not found. Install Python, or rerun with -Python C:\Path\To\python.exe."
}

function Write-CmdWrapper {
    param(
        [string] $Path,
        [string] $PythonExe,
        [string] $ScriptPath
    )

    $content = @"
@echo off
setlocal
"$PythonExe" "$ScriptPath" %*
"@
    Set-Content -LiteralPath $Path -Value $content -Encoding ASCII
}

function Invoke-Checked {
    param(
        [string] $FilePath,
        [string[]] $Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

$sourceDir = $PSScriptRoot
$prefixPath = [System.IO.Path]::GetFullPath($Prefix)
$installRoot = Join-Path $prefixPath "lib\agentrelay"
$venvPath = Join-Path $installRoot ".venv"
$binPath = Join-Path $prefixPath "bin"
$logPath = Join-Path $prefixPath "logs"
$configPath = Join-Path $HOME ".config\agentrelay\config.yaml"

$pythonExe = Resolve-AgentRelayPython -RequestedPython $Python -SourceDir $sourceDir

Write-Host "==> using Python: $pythonExe"
Write-Host "==> installing to: $prefixPath"

New-Item -ItemType Directory -Force -Path $installRoot, $binPath, $logPath | Out-Null

Write-Host "==> creating venv at $venvPath"
Invoke-Checked $pythonExe @("-m", "venv", $venvPath)

$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "venv Python was not created at $venvPython"
}

Write-Host "==> installing dependencies"
Invoke-Checked $venvPython @("-m", "pip", "install", "--quiet", "-r", (Join-Path $sourceDir "requirements.txt"))

Write-Host "==> installing files"
Copy-Item -LiteralPath (Join-Path $sourceDir "agentrelay.py") -Destination (Join-Path $installRoot "agentrelay.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "agent-send") -Destination (Join-Path $installRoot "agent-send") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "agent-talk") -Destination (Join-Path $installRoot "agent-talk") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "talk.py") -Destination (Join-Path $installRoot "talk.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "pairing.py") -Destination (Join-Path $installRoot "pairing.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "config_io.py") -Destination (Join-Path $installRoot "config_io.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "agent-forward") -Destination (Join-Path $installRoot "agent-forward") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "agentrelay_gui.py") -Destination (Join-Path $installRoot "agentrelay_gui.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "agentrelay_web.py") -Destination (Join-Path $installRoot "agentrelay_web.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "agentrelay_app.py") -Destination (Join-Path $installRoot "agentrelay_app.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "relay_client.py") -Destination (Join-Path $installRoot "relay_client.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "gui_paths.py") -Destination (Join-Path $installRoot "gui_paths.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "instance_lock.py") -Destination (Join-Path $installRoot "instance_lock.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "yolo_flags.py") -Destination (Join-Path $installRoot "yolo_flags.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "pty_session.py") -Destination (Join-Path $installRoot "pty_session.py") -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "pty_unix.py") -Destination (Join-Path $installRoot "pty_unix.py") -Force
if (Test-Path -LiteralPath (Join-Path $sourceDir "pty_windows.py")) {
    Copy-Item -LiteralPath (Join-Path $sourceDir "pty_windows.py") -Destination (Join-Path $installRoot "pty_windows.py") -Force
}
if (Test-Path -LiteralPath (Join-Path $sourceDir "terminal_pane.py")) {
    Copy-Item -LiteralPath (Join-Path $sourceDir "terminal_pane.py") -Destination (Join-Path $installRoot "terminal_pane.py") -Force
}
Copy-Item -LiteralPath (Join-Path $sourceDir "gui") -Destination (Join-Path $installRoot "gui") -Recurse -Force
if (Test-Path -LiteralPath (Join-Path $sourceDir "docs")) {
    Copy-Item -LiteralPath (Join-Path $sourceDir "docs") -Destination (Join-Path $installRoot "docs") -Recurse -Force
}

$agentrelayCmd = Join-Path $binPath "agentrelay.cmd"
$agentSendCmd = Join-Path $binPath "agent-send.cmd"
$agentTalkCmd = Join-Path $binPath "agent-talk.cmd"
$agentForwardCmd = Join-Path $binPath "agent-forward.cmd"
$agentrelayGuiCmd = Join-Path $binPath "agentrelay-gui.cmd"
Write-CmdWrapper -Path $agentrelayCmd -PythonExe $venvPython -ScriptPath (Join-Path $installRoot "agentrelay.py")
Write-CmdWrapper -Path $agentSendCmd -PythonExe $venvPython -ScriptPath (Join-Path $installRoot "agent-send")
Write-CmdWrapper -Path $agentTalkCmd -PythonExe $venvPython -ScriptPath (Join-Path $installRoot "agent-talk")
Write-CmdWrapper -Path $agentForwardCmd -PythonExe $venvPython -ScriptPath (Join-Path $installRoot "agent-forward")
Write-CmdWrapper -Path $agentrelayGuiCmd -PythonExe $venvPython -ScriptPath (Join-Path $installRoot "agentrelay_gui.py")

Write-Host "==> generating config if missing"
if (-not (Test-Path -LiteralPath $configPath)) {
    Invoke-Checked $agentrelayCmd @("--init")
} else {
    Write-Host "config exists, not overwriting: $configPath"
}

if ($Service) {
    Write-Host "==> configuring Windows service"
    $nssm = Get-Command nssm -ErrorAction SilentlyContinue
    if (-not $nssm) {
        Write-Warning "NSSM was not found. Install NSSM, add it to PATH, then rerun with -Service."
        Write-Host "Manual service command after NSSM is installed:"
        Write-Host "  nssm install $ServiceName `"$agentrelayCmd`""
    } else {
        $existing = & $nssm.Source status $ServiceName 2>$null
        if ($LASTEXITCODE -eq 0 -and -not $Force) {
            throw "Service '$ServiceName' already exists. Rerun with -Force to replace it."
        }
        if ($LASTEXITCODE -eq 0 -and $Force) {
            & $nssm.Source stop $ServiceName 2>$null | Out-Null
            & $nssm.Source remove $ServiceName confirm | Out-Null
        }
        & $nssm.Source install $ServiceName $agentrelayCmd | Out-Null
        & $nssm.Source set $ServiceName AppDirectory $installRoot | Out-Null
        & $nssm.Source set $ServiceName AppStdout (Join-Path $logPath "agentrelay.out.log") | Out-Null
        & $nssm.Source set $ServiceName AppStderr (Join-Path $logPath "agentrelay.err.log") | Out-Null
        & $nssm.Source start $ServiceName | Out-Null
        Write-Host "Windows service started: $ServiceName"
    }
}

Write-Host ""
Write-Host "Done."
Write-Host "  agentrelay     -> $agentrelayCmd"
Write-Host "  agent-send     -> $agentSendCmd"
Write-Host "  agent-talk     -> $agentTalkCmd"
Write-Host "  agent-forward  -> $agentForwardCmd"
Write-Host "  agentrelay-gui -> $agentrelayGuiCmd"
Write-Host "  config     -> $configPath"
Write-Host ""
Write-Host "Add this directory to PATH if you want global commands:"
Write-Host "  $binPath"
Write-Host ""
Write-Host "Optional — Desktop shortcut:"
Write-Host "  .\scripts\install-desktop-launcher.ps1"
