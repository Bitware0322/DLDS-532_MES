# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件 Windows 可执行程序（PyInstaller 6.x）。

执行： pyinstaller DLDS532_OrderApp.spec --noconfirm
输出： dist/DLDS532_OrderApp.exe
"""
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ["snap7"] + collect_submodules("snap7")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "pydoc_data", "test", "pytest",
        "numpy", "PIL", "matplotlib", "pandas",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DLDS532_OrderApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon="assets/app.ico",
)
