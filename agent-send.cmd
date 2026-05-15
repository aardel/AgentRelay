@echo off
setlocal
set "ROOT=%~dp0"
"%ROOT%.venv\Scripts\python.exe" "%ROOT%agent-send" --config "%ROOT%config.yaml" %*
