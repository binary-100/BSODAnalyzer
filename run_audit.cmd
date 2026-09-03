@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\run_audit.ps1" %*
exit /b %ERRORLEVEL%
