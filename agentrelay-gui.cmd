@echo off
setlocal
set "ROOT=%~dp0"
"%ROOT%.venv\Scripts\python.exe" "%ROOT%agentrelay_gui.py" --config "%ROOT%config.yaml" %*
