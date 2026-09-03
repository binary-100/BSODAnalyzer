@echo off
REM Agent / CI build — no interactive pause (see scripts\build_pause_policy.bat)

cd /d "%~dp0"
set BUILD_NOPAUSE=1
call build_and_deploy_v6.bat --no-pause
exit /b %ERRORLEVEL%
