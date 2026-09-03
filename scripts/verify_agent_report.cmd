@echo off
REM Verify agent gate proof — e.g. verify_agent_report.cmd --require facade,t2,t4
cd /d "%~dp0.."
py -3 scripts\verify_agent_report.py %*
exit /b %errorlevel%
