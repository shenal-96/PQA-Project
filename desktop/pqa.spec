# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — PQA Windows desktop app (onedir).
#
# Build from the repo root (after building the web UI):
#     cd web && npm ci && npm run build && cd ..
#     pyinstaller desktop/pqa.spec --noconfirm
#
# Produces dist/PQA/PQA.exe plus its _internal payload (incl. the single-file web UI).
# console=True for now so first runs surface tracebacks; flip to False once verified.
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.getcwd())

# Bundle the built web UI at <bundle>/web/dist/ (a single self-contained index.html).
datas = [(os.path.join(ROOT, "web", "dist"), os.path.join("web", "dist"))]
binaries = []
hiddenimports = ["core", "core.analysis", "core.serialize", "core.viz_dataprep"]

# pywebview + its Windows EdgeChromium (WebView2) backend and pythonnet glue.
_d, _b, _h = collect_all("webview")
datas += _d
binaries += _b
hiddenimports += _h + collect_submodules("webview")

a = Analysis(
    [os.path.join("desktop", "shell.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["streamlit", "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PQA",
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PQA")
