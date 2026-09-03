@echo off
set "REPO=%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\.cursor\AgentStarterPack\pack\scripts\sync-audit-system.ps1" -ProjectRoot "%REPO%" %*
if errorlevel 1 if exist "%USERPROFILE%\OneDrive\Desktop\AgentStarterPack\pack\scripts\sync-audit-system.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\OneDrive\Desktop\AgentStarterPack\pack\scripts\sync-audit-system.ps1" -ProjectRoot "%REPO%" %*
)
if errorlevel 1 if exist "%USERPROFILE%\.cursor\agent-starter-pack\pack\scripts\sync-audit-system.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\.cursor\agent-starter-pack\pack\scripts\sync-audit-system.ps1" -ProjectRoot "%REPO%" %*
)
if errorlevel 1 if exist "%USERPROFILE%\OneDrive\Desktop\CursorAgentStarterPack\pack\scripts\sync-audit-system.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\OneDrive\Desktop\CursorAgentStarterPack\pack\scripts\sync-audit-system.ps1" -ProjectRoot "%REPO%" %*
)
exit /b %ERRORLEVEL%
