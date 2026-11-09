# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).resolve().parent
app_icon = project_root / "assets" / "brand" / "app_icon.ico"
app_manifest = project_root / "build" / "app.manifest"
app_version = project_root / "build" / "version_info.txt"
brand_assets = project_root / "assets" / "brand"
software_name = "奶蛙的荣光"

voice_datas = []
voice_binaries = []
voice_hiddenimports = []
for package_name in ("sherpa_onnx",):
    package_datas, package_binaries, package_hiddenimports = collect_all(
        package_name
    )
    voice_datas += package_datas
    voice_binaries += package_binaries
    voice_hiddenimports += package_hiddenimports
voice_hiddenimports.extend(
    (
        "sounddevice",
        "webrtcvad",
        "_webrtcvad",
        "_cffi_backend",
    )
)

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root / "src")],
    binaries=voice_binaries,
    datas=[
        (str(brand_assets), "assets/brand"),
        (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
        (str(project_root / "DISCLAIMER.md"), "."),
        *voice_datas,
    ],
    hiddenimports=voice_hiddenimports,
    hookspath=[str(project_root / "build" / "pyinstaller_hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "official_web_diagnostic_build",
        "official_web_diagnostics",
        "official_web_browser_host",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebChannel",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=software_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(app_icon),
    manifest=str(app_manifest),
    version=str(app_version),
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=software_name,
)
