# -*- mode: python ; coding: utf-8 -*-
# Сборка: uv run pyinstaller simple_pyramid.spec --noconfirm  →  dist/simple_pyramid/
# Одинаково локально и в CI (раньше команды отличались именем exe).
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["src/simple_pyramid/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[("src/simple_pyramid/ui", "simple_pyramid/ui")],
    hiddenimports=[
        *collect_submodules("simple_pyramid"),
        *collect_submodules("keyring.backends"),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "fastapi", "uvicorn", "respx", "mypy"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="simple_pyramid",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["installer\\favicon.ico"],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="simple_pyramid",
)
