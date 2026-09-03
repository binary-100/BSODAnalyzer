@echo off
cd /d "%~dp0.."
py -3 "%USERPROFILE%\.cursor\AgentStarterPack\pack\scripts\audit_code_checks.py" "%CD%" --write-semantic-template
exit /b %ERRORLEVEL%
