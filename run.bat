@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
python -m deadlock_advisor %*
if errorlevel 1 pause
