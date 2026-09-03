@echo off
REM BSOD Analyzer factory (Model A): refresh pack context, then strip generic rules from the project.
REM Generic rules stay in %%USERPROFILE%%\.cursor\rules\ — avoids duplicate/conflicting always-on context.
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo [Model A] Running pack refresh...
call "%ROOT%\Refresh-AgentContext.cmd" %*
if errorlevel 1 exit /b 1

echo [Model A] Pruning generic rules from project .cursor\rules\ ...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\prune_factory_generic_rules.ps1" -ProjectRoot "%ROOT%"
if errorlevel 1 exit /b 1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\prune_factory_generic_rules.ps1" -ProjectRoot "%ROOT%" -VerifyOnly
exit /b %ERRORLEVEL%
