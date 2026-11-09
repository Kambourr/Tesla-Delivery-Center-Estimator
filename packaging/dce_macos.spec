# -*- mode: python ; coding: utf-8 -*-
"""Unsigned macOS Apple Silicon app.

Run this spec only through ``scripts/build_macos.sh`` on an arm64 Mac.
PyInstaller names below (``Analysis``, ``PYZ``, ``EXE``, ``COLLECT``,
``BUNDLE``, ``SPECPATH``) are injected by PyInstaller. Do not pass
``cipher``: PyInstaller 6 removed that argument.
"""

from pathlib import Path

root = Path(SPECPATH).resolve().parent

datas = [
    (str(root / "src" / "dce" / "app" / "web"), "dce/app/web"),
    (str(root / "data" / "seed"), "data/seed"),
    (str(root / "data" / "defaults"), "data/defaults"),
    (str(root / "data" / "demo"), "data/demo"),
    (str(root / "tests" / "fixtures" / "hud_9440x.json"), "tests/fixtures/hud_9440x.json"),
]

a = Analysis(
    [str(root / "src" / "dce" / "app" / "__main__.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["webview", "yaml", "bottle"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeliveryCenterEstimator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DeliveryCenterEstimator",
)
app = BUNDLE(
    coll,
    name="DeliveryCenterEstimator.app",
    bundle_identifier="edu.deliverycenter.estimator",
    info_plist={
        "CFBundleName": "Delivery Center Estimator",
        "CFBundleDisplayName": "Delivery Center Estimator",
        "CFBundleShortVersionString": "0.0.0",
        "NSHighResolutionCapable": True,
    },
)
