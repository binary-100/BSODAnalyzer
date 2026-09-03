@echo off

REM Build BSOD Analyzer v5 maintenance (5.4.x) — AMD logo fix only.

REM Does not include v6 catalog / MSCatalogLTS work. Restores v6.0.0 dev version after build.



cd /d "%~dp0"
call scripts\build_pause_policy.bat %*

if exist "dist\v5_build\BSODAnalyzer" (
    echo Clearing previous v5 build output...
    taskkill /IM BSODAnalyzer.exe /F >nul 2>&1
    rmdir /S /Q "dist\v5_build\BSODAnalyzer" 2>nul
)

echo [v5] Applying version 5.4.13...

py -3 scripts\apply_version.py 5.4.13

if errorlevel 1 exit /b 1



echo [v5] Building AMD logo PNG (requires approved reference)...

py -3 scripts\build_amd_logo_png.py --skip-if-current

if errorlevel 1 (

    echo AMD logo build failed — place reference at preview_amd_logos\FROM_YOUR_REFERENCE.png

    py -3 scripts\apply_version.py 6

    if "%BUILD_NOPAUSE%"=="" pause

    exit /b 1

)



echo [v5] Running v5 test subset...

call run_tests_v5.bat

if errorlevel 1 (

    py -3 scripts\apply_version.py 6

    if "%BUILD_NOPAUSE%"=="" pause

    exit /b 1

)



for /f "tokens=2 delims=: " %%V in ('findstr /B "Version:" VERSION.txt') do set "PRODUCT_VER=%%V"

echo Building BSOD Analyzer v%PRODUCT_VER% maintenance (onedir, v5 spec)...



pyinstaller BSODAnalyzer.v5.spec --distpath "dist\v5_build" --noconfirm

if errorlevel 1 (

    py -3 scripts\apply_version.py 6

    echo Build failed.

    if "%BUILD_NOPAUSE%"=="" pause

    exit /b 1

)



set "SRC=dist\v5_build\BSODAnalyzer"

set "DST=BSODAnalyzer_v5"



if not exist "%DST%" mkdir "%DST%"

if not exist "%SRC%\BSODAnalyzer.exe" (

    py -3 scripts\apply_version.py 6

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

    py -3 scripts\apply_version.py 6

    if "%BUILD_NOPAUSE%"=="" pause

    exit /b 1

)



echo Syncing DebuggingTools to %DST% (excludes sym cache)...

if exist "DebuggingTools" (

    if not exist "%DST%\DebuggingTools" mkdir "%DST%\DebuggingTools"

    robocopy "DebuggingTools" "%DST%\DebuggingTools" /E /XD sym ttd /NFL /NDL /NJH /NJS /NP >nul

)



if not exist "%DST%\DebuggingTools\Installers" mkdir "%DST%\DebuggingTools\Installers"

if not exist "%DST%\DebuggingTools\Installers\winsdksetup.exe" (

    if exist "DebuggingTools\Installers\winsdksetup.exe" (

        copy /Y "DebuggingTools\Installers\winsdksetup.exe" "%DST%\DebuggingTools\Installers\" >nul

    )

)



echo Post-build portable smoke (v5)...

set "BSOD_PORTABLE_POSTBUILD=1"

set "BSOD_PRODUCT_LINE=v5"

set "PYTHONPATH=%CD%"

py -3 tests\test_portable_build_smoke.py

if errorlevel 1 (

    py -3 scripts\apply_version.py 6

    if "%BUILD_NOPAUSE%"=="" pause

    exit /b 1

)



echo Restoring development version 6.0.0 in source tree...

py -3 scripts\apply_version.py 6



echo Done. %DST%\BSODAnalyzer.exe is v%PRODUCT_VER% maintenance build.
exit /b 0

