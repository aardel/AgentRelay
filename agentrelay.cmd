@echo off
setlocal
set "ROOT=%~dp0"
"%ROOT%.venv\Scripts\python.exe" "%ROOT%agentrelay.py" --config "%ROOT%config.yaml" %*
