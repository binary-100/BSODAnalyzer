@echo off
REM Sync this project's agent context from Agent Starter Pack (rules + audit templates + refresh brief).
REM No arguments required - this folder is the agent root (contains AGENTS.md).
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PS1="
if exist "%USERPROFILE%\.cursor\AgentStarterPack\pack\scripts\refresh-agent-context.ps1" (
  set "PS1=%USERPROFILE%\.cursor\AgentStarterPack\pack\scripts\refresh-agent-context.ps1"
)
if not defined PS1 if exist "%USERPROFILE%\OneDrive\Desktop\AgentStarterPack\pack\scripts\refresh-agent-context.ps1" (
  set "PS1=%USERPROFILE%\OneDrive\Desktop\AgentStarterPack\pack\scripts\refresh-agent-context.ps1"
)
if not defined PS1 (
  echo ERROR: Agent Starter Pack not found. Run Install-AgentStarterPack.cmd once on this PC.
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -ProjectRoot "%ROOT%" %*
exit /b %ERRORLEVEL%
