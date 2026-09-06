@echo off
REM Run all BSOD Analyzer unit/regression tests (Phase 1 — does not ship in the exe).

cd /d "%~dp0"
set "PYTHONPATH=%CD%"
set "QT_QPA_PLATFORM=offscreen"
set "PYTHONSTARTUP=%CD%\tests\_qt_startup.py"
set "FAILED=0"

echo Syncing VERSION.txt from bsod_analyzer.VERSION...
py -3 scripts\apply_version.py sync
if errorlevel 1 (
    echo Version sync failed — fix bsod_analyzer.VERSION or scripts\apply_version.py
    exit /b 1
)

py -3 -c "import pytest" 2>nul
if errorlevel 1 (
    echo pytest is required for test discovery — install with: py -3 -m pip install pytest
    exit /b 1
)

echo BSOD Analyzer test suite (PYTHONPATH=%CD%)
echo.

echo === Harness gates (discovery + static analysis) ===
call :run_one "tests\test_test_discovery.py"
call :run_one "tests\test_static_analysis.py"
echo.

for %%f in (tests\test_*.py) do (
    if /I not "%%~nf"=="test_test_discovery" if /I not "%%~nf"=="test_static_analysis" call :run_one "%%f"
)

if "%FAILED%"=="1" (
    echo One or more tests failed.
    exit /b 1
)

echo All tests passed.

py -3 -c "import sys; sys.path.insert(0, r'scripts'); from agent_gate_proof import record_gate; record_gate('t2', cmd='run_tests.bat', all_passed=True)"

for /d /r "%CD%" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul

exit /b 0

REM Run one test file. Uses an explicit ERRORLEVEL comparison, not "if errorlevel 1":
REM that form means ">= 1", so an interpreter crash (0xC0000005 access violation,
REM 0xC0000409 stack overrun) returns a negative code and was reported as OK.
:run_one
echo === %~1 ===
py -3 tests\run_test_module.py "%~1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" if /I "%~nx1"=="test_workflow_copy_batch4.py" (
    echo Retrying %~1 ^(Qt offscreen teardown flake^)...
    py -3 tests\run_test_module.py "%~1"
    set "RC=%ERRORLEVEL%"
)
REM pytest's final progress line has no trailing newline, so without this the verdict
REM gets appended to it ("....F.FAILED: tests\x.py") and is missed when scanning the log.
echo.
if not "%RC%"=="0" (
    echo FAILED: %~1 [exit %RC%]
    set "FAILED=1"
) else (
    echo OK: %~1
)
echo.
goto :eof
