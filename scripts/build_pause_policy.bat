@echo off
REM Configure BUILD_NOPAUSE for non-interactive runs (CI, agents, piped stdin).
REM Interactive double-click / local cmd: pauses remain on failure unless BUILD_NOPAUSE=1.
REM Override: set BUILD_FORCE_PAUSE=1 to always pause; pass --no-pause to skip pauses.

if defined BUILD_FORCE_PAUSE exit /b 0
if defined BUILD_NOPAUSE exit /b 0

if /i "%~1"=="--no-pause" set BUILD_NOPAUSE=1& exit /b 0
if /i "%~2"=="--no-pause" set BUILD_NOPAUSE=1& exit /b 0

if defined CI set BUILD_NOPAUSE=1& exit /b 0
if defined GITHUB_ACTIONS set BUILD_NOPAUSE=1& exit /b 0
if defined TF_BUILD set BUILD_NOPAUSE=1& exit /b 0
if defined CURSOR_TRACE_ID set BUILD_NOPAUSE=1& exit /b 0
if defined CURSOR_AGENT set BUILD_NOPAUSE=1& exit /b 0

REM Stdin not a console (background / piped invocations).
py -3 -c "import sys; raise SystemExit(0 if sys.stdin.isatty() else 1)" >nul 2>&1
if errorlevel 1 set BUILD_NOPAUSE=1

exit /b 0
