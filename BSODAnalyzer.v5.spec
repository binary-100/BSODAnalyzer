# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — BSOD Analyzer v5 maintenance line (5.4.x).
# AMD logo fix only; no MSCatalogLTS / v6 catalog bundle.
# Run: pyinstaller BSODAnalyzer.v5.spec --distpath dist\v5_build --noconfirm
import os

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

_vendor_datas = []
_vendor_src = os.path.join(SPECPATH, 'assets', 'vendor_icons')
if os.path.isdir(_vendor_src):
    for _fn in os.listdir(_vendor_src):
        if _fn.lower().endswith(('.svg', '.png', '.ico')):
            _vendor_datas.append(
                (os.path.join(_vendor_src, _fn), os.path.join('assets', 'vendor_icons'))
            )

a = Analysis(
    ['bsod_analyzer.py'],
    pathex=[],
    binaries=[],
    datas=_dbg_datas + _vendor_datas,
    hiddenimports=[
        'bsod_gui_qt',
        'bsod_gui_preferences',
        'gui_vendor_icons',
        'gui_include_header',
        'PySide6.QtSvg',
        'driver_catalog',
        'firmware_catalog',
        'device_enrichment',
        'app_settings',
        'log_cleanup',
        'bsod_gui_log_cleanup',
        'driver_index',
        'driver_install',
        'hardware_cache',
        'catalog_cache',
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
    if 'debuggingtools/' in d:
        return True
    if '/qml/' in d or d.startswith('pyside6/qml/') or '/translations/' in d:
        return False
    base = d.rsplit('/', 1)[-1]
    return _drop.match(base) is None

a.binaries = [b for b in a.binaries if _keep_qt(b[0])]
a.datas = [d for d in a.datas if _keep_qt(d[0])]

pyz = PYZ(a.pure)

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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
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
