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

REM Second instance: open browser to existing UI
if exist "%TEMP%\agentrelay-gui.pid" (
  for /f %%i in (%TEMP%\agentrelay-gui.pid) do set GUI_PID=%%i
  tasklist /FI "PID eq %GUI_PID%" 2>nul | find "%GUI_PID%" >nul && (
    for /f "tokens=*" %%u in ('"%ROOT%\.venv\Scripts\python.exe" -c "import yaml; c=yaml.safe_load(open(r'%CONFIG%')); print('http://127.0.0.1:%s/?token=%s&port=%s'%%(c['port'],c['token'],c['port']))"') do start "" "%%u"
    exit /b 0
  )
)

start "" "%ROOT%\.venv\Scripts\pythonw.exe" "%ROOT%\agentrelay_gui.py" --config "%CONFIG%"
