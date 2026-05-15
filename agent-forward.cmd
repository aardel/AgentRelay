@echo off
setlocal
set "ROOT=%~dp0"
"%ROOT%.venv\Scripts\python.exe" "%ROOT%agent-forward" --config "%ROOT%config.yaml" %*
