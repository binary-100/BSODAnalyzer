# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for BSOD Analyzer v6.  Run from repo root: pyinstaller BSODAnalyzer.spec
#
# v5.4.11+: onedir build (BSODAnalyzer.exe + _internal/).  One-file mode re-reads the
# exe on every launch to unpack; that fails with Permission denied under OneDrive sync.
# CDB in DebuggingTools/x64 is still bundled into _internal for offline use.
import os

# Trim unused Qt modules to keep the bundle smaller (we only use QtCore/QtGui/QtWidgets).
_qt_excludes = [
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickWidgets',
    'PySide6.QtQuickControls2', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick', 'PySide6.QtWebChannel', 'PySide6.QtWebSockets',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtCharts',
    'PySide6.QtDataVisualization', 'PySide6.QtGraphs', 'PySide6.Qt3DCore',
    'PySide6.Qt3DRender', 'PySide6.Qt3DInput', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
    'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtPositioning', 'PySide6.QtLocation', 'PySide6.QtSensors',
    'PySide6.QtSerialPort', 'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtNetwork',
    'PySide6.QtNetworkAuth', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml',
    'PySide6.QtStateMachine', 'PySide6.QtHelp', 'PySide6.QtDesigner', 'PySide6.QtUiTools',
    'PySide6.QtConcurrent', 'PySide6.QtSpatialAudio', 'PySide6.QtTextToSpeech',
]

_dbg_datas = []
_dbg_src = os.path.join(SPECPATH, 'DebuggingTools', 'x64')
if os.path.isdir(_dbg_src):
    for _root, _dirs, _files in os.walk(_dbg_src):
        # Never bundle the symbol cache or Time Travel Debugging (huge, not needed for !analyze).
        _dirs[:] = [_d for _d in _dirs if _d.lower() not in ('sym', 'ttd')]
        if os.path.basename(_root).lower() in ('sym', 'ttd'):
            continue
        for _fn in _files:
            _full = os.path.join(_root, _fn)
            _rel = os.path.relpath(os.path.dirname(_full), _dbg_src)
            _dest = os.path.join('DebuggingTools', 'x64') if _rel == '.' else os.path.join('DebuggingTools', 'x64', _rel)
            _dbg_datas.append((_full, _dest))
else:
    raise SystemExit("DebuggingTools/x64 not found - run install/update CDB first so it can be bundled.")

_ps_datas = []
_ps_src = os.path.join(SPECPATH, 'PowerShellModules')
if os.path.isdir(_ps_src):
    for _root, _dirs, _files in os.walk(_ps_src):
        for _fn in _files:
            _full = os.path.join(_root, _fn)
            _rel = os.path.relpath(os.path.dirname(_full), _ps_src)
            _dest = os.path.join('PowerShellModules') if _rel == '.' else os.path.join('PowerShellModules', _rel)
            _ps_datas.append((_full, _dest))
else:
    raise SystemExit(
        "PowerShellModules not found - run scripts\\vendor_mscataloglts.ps1 before building."
    )

# Optional vendor logo overrides (assets/vendor_icons/*.svg|png).
_vendor_datas = []
_vendor_src = os.path.join(SPECPATH, 'assets', 'vendor_icons')
if os.path.isdir(_vendor_src):
    for _fn in os.listdir(_vendor_src):
        if _fn.lower().endswith(('.svg', '.png', '.ico')):
            _vendor_datas.append(
                (os.path.join(_vendor_src, _fn), os.path.join('assets', 'vendor_icons'))
            )

# C4 app icon (themed SVG + prebuilt PNG/ICO from scripts/build_app_icon.py).
_app_icon_datas = []
_app_icon_src = os.path.join(SPECPATH, 'assets', 'app_icon')
if os.path.isdir(_app_icon_src):
    for _fn in os.listdir(_app_icon_src):
        if _fn.lower().endswith(('.svg', '.png', '.ico')):
            _app_icon_datas.append(
                (os.path.join(_app_icon_src, _fn), os.path.join('assets', 'app_icon'))
            )

_script_datas = []
_ps7_install = os.path.join(SPECPATH, 'scripts', 'install_powershell7.ps1')
if os.path.isfile(_ps7_install):
    _script_datas.append((_ps7_install, os.path.join('scripts')))
_data_dir = os.path.join(SPECPATH, 'data')
if os.path.isdir(_data_dir):
    for _fn in os.listdir(_data_dir):
        if _fn.lower().endswith('.json'):
            _script_datas.append(
                (os.path.join(_data_dir, _fn), os.path.join('data'))
            )

_exe_icon = os.path.join(SPECPATH, 'assets', 'app_icon', 'BSODAnalyzer.ico')

a = Analysis(
    ['bsod_analyzer.py'],
    pathex=[],
    binaries=[],
    datas=_dbg_datas + _ps_datas + _vendor_datas + _app_icon_datas + _script_datas,
    hiddenimports=[
        'bsod_gui_qt',
        'bsod_gui_preferences',
        'gui_vendor_icons',
        'gui_app_icon',
        'gui_include_header',
        'gui_checkbox_style',
        'PySide6.QtSvg',
        'driver_catalog',
        'vendor_download_resolve',
        'vendor_firmware_fetch',
        'gpu_vendor_maps',
        'vendor_page_render',
        'vendor_fetch',
        'vendor_endpoint_health',
        'vendor_endpoint_audit',
        'firmware_catalog',
        'firmware_ssd_vendors',
        'firmware_peripheral_vendors',
        'firmware_peripheral_discovery',
        'firmware_peripheral_installed',
        'device_enrichment',
        'app_settings',
        'log_cleanup',
        'bsod_gui_log_cleanup',
        'driver_index',
        'driver_install',
        'hardware_cache',
        'catalog_cache',
        'catalog_ps_module',
        'product_version',
        'maintenance_log',
        'bsod_runtime',
        'bsod_events',
        'bsod_hardware_wmi',
        'bsod_gui_workers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hooks/pyi_rth_cli_console.py'],
    excludes=_qt_excludes,
    noarchive=False,
    optimize=0,
)
# Drop Qt binaries/data this static QtWidgets app never uses (keeps the bundle ~30 MB smaller).
import re as _re
_drop = _re.compile(
    r'^(?:'
    r'qt6quick.*|qt6qml.*|qt6pdf.*|qt6webengine.*|qt6webchannel.*|qt6websockets.*|'
    r'qt63d.*|qt6charts.*|qt6datavisualization.*|qt6graphs.*|qt6multimedia.*|'
    r'qt6virtualkeyboard.*|qt6designer.*|qt6test.*|qt6sql.*|qt6positioning.*|'
    r'qt6location.*|qt6sensors.*|qt6serialport.*|qt6bluetooth.*|qt6nfc.*|'
    r'qt6remoteobjects.*|qt6scxml.*|qt6statemachine.*|qt6spatialaudio.*|qt6texttospeech.*|'
    r'opengl32sw\.dll|d3dcompiler_47\.dll|'
    r'qtquick.*|qtqml.*|qtpdf.*|qtwebengine.*|qt3d.*|qtcharts.*|qtmultimedia.*|'
    r'qtdatavisualization.*|qtpositioning.*|qtlocation.*|qtsensors.*|qtserialport.*|'
    r'qtbluetooth.*|qtnfc.*|qtremoteobjects.*|qtscxml.*|qtstatemachine.*|qtsql.*|'
    r'qttest.*|qtdesigner.*|qttexttospeech.*|qtspatialaudio.*'
    r')$'
)

def _keep_qt(dest):
    d = str(dest).replace('\\', '/').lower()
    # Never filter out the bundled Debugging Tools.
    if 'debuggingtools/' in d:
        return True
    if 'powershellmodules/' in d:
        return True
    if '/qml/' in d or d.startswith('pyside6/qml/') or '/translations/' in d:
        return False
    base = d.rsplit('/', 1)[-1]
    return _drop.match(base) is None

a.binaries = [b for b in a.binaries if _keep_qt(b[0])]
a.datas = [d for d in a.datas if _keep_qt(d[0])]

pyz = PYZ(a.pure)

# Onedir: launcher exe plus _internal/ folder (avoids OneDrive lock on self-extract).
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BSODAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # No console window when launching GUI (cleaner for end users)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon=_exe_icon if os.path.isfile(_exe_icon) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=['cdb.exe', 'dbgeng.dll', 'dbghelp.dll', 'symsrv.dll'],
    name='BSODAnalyzer',
)
