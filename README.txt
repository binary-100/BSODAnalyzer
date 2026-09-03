BSOD Analyzer — source tree
============================

Current release: see VERSION.txt → portable folder BSODAnalyzer_v6\

Run tests: run_tests.bat

Run the app:
  BSODAnalyzer_v6\BSODAnalyzer.exe
  (recommended) BSODAnalyzer_v6\Run BSODAnalyzer as Administrator.bat

Build after code changes:
  set BUILD_NOPAUSE=1
  call build_ci.bat

Source: Python modules in this folder (bsod_analyzer.py, bsod_gui_qt.py, …).
Bundled CDB for PyInstaller: DebuggingTools\x64\

See VERSION.txt and VERSIONING.md for release notes and layout.
