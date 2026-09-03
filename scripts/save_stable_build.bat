@echo off
REM Archive a USER-APPROVED BSODAnalyzer_v6 build outside the dev tree.
REM Do NOT call from build_and_deploy_v6.bat — only after field testing on real hardware.
REM Usage:
REM   scripts\save_stable_build.bat          — archive to Desktop\BSODAnalyzer_StableBuilds\vX.Y.Z\
REM   scripts\save_stable_build.bat /Force   — replace an existing archive for the same version

cd /d "%~dp0.."

set "SRC=BSODAnalyzer_v6"
set "FORCE=0"
:parse_args
if /I "%~1"=="/Force" set "FORCE=1" & shift & goto parse_args
if not "%~1"=="" shift & goto parse_args

if not exist "%SRC%\BSODAnalyzer.exe" (
    echo Missing %SRC%\BSODAnalyzer.exe — build first with build_and_deploy_v6.bat
    exit /b 1
)

for /f "tokens=2 delims=: " %%V in ('findstr /B "Version:" VERSION.txt 2^>nul') do set "VER=%%V"
if not defined VER for /f %%V in ('py -3 -c "import bsod_analyzer as c; print(c.VERSION)" 2^>nul') do set "VER=%%V"
if not defined VER set "VER=unknown"

REM Stable builds live on the Desktop (OneDrive-redirected if present, else classic).
set "DESKTOP=%USERPROFILE%\OneDrive\Desktop"
if not exist "%DESKTOP%" set "DESKTOP=%USERPROFILE%\Desktop"
set "ARCHIVE_ROOT=%DESKTOP%\BSODAnalyzer_StableBuilds"
set "ARCHIVE=%ARCHIVE_ROOT%\v%VER%"

echo Saving stable build v%VER% ...
echo   Source:  %CD%\%SRC%\
echo   Archive: %ARCHIVE%\

if exist "%ARCHIVE%\BSODAnalyzer.exe" if "%FORCE%"=="0" (
    echo.
    echo Archive already exists for v%VER% — not overwritten.
    echo Use /Force to replace it, or bump VERSION before saving a new stable.
    goto write_pointer
)

taskkill /IM BSODAnalyzer.exe /F >nul 2>&1
timeout /t 1 /nobreak >nul 2>&1

if not exist "%ARCHIVE_ROOT%" mkdir "%ARCHIVE_ROOT%"

echo Finalizing portable layout before archive...
py -3 scripts\finalize_portable_dist.py "%SRC%"
if errorlevel 1 exit /b 1

if exist "%ARCHIVE%" if "%FORCE%"=="1" (
    echo Replacing existing archive ^(/Force^)...
    rmdir /S /Q "%ARCHIVE%" 2>nul
)

mkdir "%ARCHIVE%" 2>nul
robocopy "%SRC%" "%ARCHIVE%" /E /NFL /NDL /NJH /NJS /NP /XD driver_catalog >nul
if errorlevel 8 (
    echo Robocopy failed copying stable build.
    exit /b 1
)

copy /Y "VERSION.txt" "%ARCHIVE%\" >nul 2>&1

(
    echo BSOD Analyzer stable archive
    echo Version: %VER%
    echo Saved: %DATE% %TIME%
    echo Source folder: %CD%\%SRC%\
    echo.
    echo This folder is outside the development tree and is not modified by build_and_deploy_v6.bat.
    echo Older versions remain in: %ARCHIVE_ROOT%\
) > "%ARCHIVE%\STABLE_BUILD.txt"

:write_pointer
(
    echo %ARCHIVE%
    echo Version: %VER%
    echo Updated: %DATE% %TIME%
) > "STABLE_BUILD_LOCATION.txt"

echo Done. Stable archive: %ARCHIVE%\BSODAnalyzer.exe
exit /b 0
