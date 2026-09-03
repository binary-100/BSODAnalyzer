@echo off
cd /d "%~dp0.."
py -3 "%USERPROFILE%\.cursor\AgentStarterPack\pack\scripts\audit_code_checks.py" "%CD%" --verify-semantic-report
if errorlevel 1 exit /b 1
exit /b 0
