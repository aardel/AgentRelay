@echo off
setlocal
REM Desktop / shortcut launcher for Windows

if defined AGENTRELAY_ROOT (
  set "ROOT=%AGENTRELAY_ROOT%"
) else if exist "%USERPROFILE%\AgentRelay\agentrelay.py" (
  set "ROOT=%USERPROFILE%\AgentRelay"
) else (
  set "ROOT=%~dp0.."
)

cd /d "%ROOT%"
if not exist "%ROOT%\.venv\Scripts\python.exe" (
  python -m venv .venv
  "%ROOT%\.venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)

set "CONFIG=%AGENTRELAY_CONFIG%"
if not defined CONFIG set "CONFIG=%ROOT%\config.yaml"

if not exist "%CONFIG%" (
  "%ROOT%\.venv\Scripts\python.exe" "%ROOT%\agentrelay.py" --init --config "%CONFIG%"
)

REM Single GUI instance (second click opens browser via agentrelay_gui.py PID lock)
start "" "%ROOT%\.venv\Scripts\pythonw.exe" "%ROOT%\agentrelay_gui.py" --config "%CONFIG%"
