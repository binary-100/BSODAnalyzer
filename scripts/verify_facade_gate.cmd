@echo off
REM Facade / orchestration gate (AGENT_READINESS T3) + machine proof record.
cd /d "%~dp0.."
py -3 scripts\verify_facade_gate.py
exit /b %errorlevel%
