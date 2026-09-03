@echo off
setlocal EnableDelayedExpansion
REM v5 maintenance tests — excludes v6-only catalog / MSCatalogLTS tests.

cd /d "%~dp0"
set PYTHONPATH=%CD%

for %%f in (tests\test_*.py) do (
    set "SKIP=0"
    if /i "%%~nxf"=="test_catalog_ps_module.py" set "SKIP=1"
    if /i "%%~nxf"=="test_driver_scan_progress.py" set "SKIP=1"
    if /i "%%~nxf"=="test_product_version.py" set "SKIP=1"
    if "!SKIP!"=="0" (
        echo Running %%f ...
        py "%%f"
        if errorlevel 1 exit /b 1
    )
)
echo v5 test subset OK
exit /b 0
