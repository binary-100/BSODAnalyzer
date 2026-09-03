@echo off
REM Build BSOD Analyzer v6.x (driver catalog overhaul, MSCatalogLTS, etc.)

cd /d "%~dp0"
call scripts\build_pause_policy.bat %*

if exist "dist\v6_build\BSODAnalyzer" (
    echo Clearing previous v6 build output...
    taskkill /IM BSODAnalyzer.exe /F >nul 2>&1
    rmdir /S /Q "dist\v6_build\BSODAnalyzer" 2>nul
)

echo Running tests before v6 build...
call run_tests.bat
if errorlevel 1 (
    echo Tests failed — build aborted.
    if "%BUILD_NOPAUSE%"=="" pause
    exit /b 1
)

py -3 scripts\apply_version.py sync
if errorlevel 1 exit /b 1

echo Ensuring AMD vendor icon (assets\vendor_icons\amd.png)...
py -3 scripts\build_amd_logo_png.py --skip-if-current
if errorlevel 1 (
    echo AMD logo build failed.
    if "%BUILD_NOPAUSE%"=="" pause
    exit /b 1
)

echo Ensuring C4 app icon (assets\app_icon\BSODAnalyzer.ico)...
py -3 scripts\build_app_icon.py
if errorlevel 1 (
    echo App icon build failed.
    if "%BUILD_NOPAUSE%"=="" pause
    exit /b 1
)

for /f "tokens=2 delims=: " %%V in ('findstr /B "Version:" VERSION.txt') do set "PRODUCT_VER=%%V"
echo Building BSOD Analyzer v%PRODUCT_VER% (onedir, with bundled CDB + MSCatalogLTS)...

if not exist "PowerShellModules\MSCatalogLTS" (
    echo Vendoring MSCatalogLTS...
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\vendor_mscataloglts.ps1
    if errorlevel 1 (
        echo MSCatalogLTS vendor failed.
        if "%BUILD_NOPAUSE%"=="" pause
        exit /b 1
    )
)

py -3 -m PyInstaller BSODAnalyzer.spec --distpath "dist\v6_build" --noconfirm
if errorlevel 1 (
    echo Build failed.
    if "%BUILD_NOPAUSE%"=="" pause
    exit /b 1
)

set "SRC=dist\v6_build\BSODAnalyzer"
set "DST=BSODAnalyzer_v6"

if not exist "%DST%" mkdir "%DST%"

echo Cleaning stale portable root folders from prior builds...
py -3 scripts\finalize_portable_dist.py --clean-only "%DST%" 2>nul

if not exist "%SRC%\BSODAnalyzer.exe" (
    echo Missing build output: %SRC%\BSODAnalyzer.exe
    if "%BUILD_NOPAUSE%"=="" pause
    exit /b 1
)

copy /Y "%SRC%\BSODAnalyzer.exe" "%DST%\"
if exist "%DST%\_internal" rmdir /S /Q "%DST%\_internal"
robocopy "%SRC%\_internal" "%DST%\_internal" /E /NFL /NDL /NJH /NJS /NP >nul

copy /Y "VERSION.txt" "%DST%\" >nul 2>&1

echo Syncing README.txt for v%PRODUCT_VER%...
py -3 scripts\sync_dist_readme.py "%DST%"
if errorlevel 1 (
    if "%BUILD_NOPAUSE%"=="" pause
    exit /b 1
)

echo Finalizing portable layout (hide runtime, seed exports folder)...
py -3 scripts\finalize_portable_dist.py "%DST%"
if errorlevel 1 (
    if "%BUILD_NOPAUSE%"=="" pause
    exit /b 1
)

echo Post-build portable smoke (v6)...
set "BSOD_PORTABLE_POSTBUILD=1"
set "BSOD_PRODUCT_LINE=v6"
set "PYTHONPATH=%CD%"
py -3 tests\test_portable_build_smoke.py
if errorlevel 1 (
    if "%BUILD_NOPAUSE%"=="" pause
    exit /b 1
)

echo Re-finalizing portable layout after smoke tests...
py -3 scripts\finalize_portable_dist.py "%DST%"
if errorlevel 1 (
    if "%BUILD_NOPAUSE%"=="" pause
    exit /b 1
)

echo Done. %DST%\BSODAnalyzer.exe (+ hidden _internal\) is the v%PRODUCT_VER% build.
echo.
echo Stable archive: NOT saved automatically. Field-test this build first.
echo When approved, run manually from app\:
echo   scripts\save_stable_build.bat /Force
echo Keeps at most 3 approved versions in Desktop\BSODAnalyzer_StableBuilds\

exit /b 0
