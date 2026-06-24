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
# core engine + report path (report/html_report/visualizations are imported lazily
# by string from desktop.report_host, so PyInstaller needs them declared here).
hiddenimports = [
    "core", "core.analysis", "core.serialize", "core.viz_dataprep", "core.recalc",
    "desktop.report_host", "desktop.viz_report", "desktop.xls_host",
    "desktop.template_store", "desktop.usage_log", "desktop.crash_report",
    "report", "html_report", "visualizations",
    # XLS tabs (lazily string-imported from desktop.xls_host).
    "ecu_parser", "ecu_csv_parser", "ecu_multi_comparator", "ecu_csv_comparator",
    "ecu_recording_parser", "python_calamine",
    "docx", "PIL",
]

# pywebview + its Windows EdgeChromium (WebView2) backend and pythonnet glue.
_d, _b, _h = collect_all("webview")
datas += _d
binaries += _b
hiddenimports += _h + collect_submodules("webview")

# matplotlib renders the report images host-side; bundle its data (fonts, etc.).
_md, _mb, _mh = collect_all("matplotlib")
datas += _md
binaries += _mb
hiddenimports += _mh

a = Analysis(
    # Absolute path: PyInstaller resolves relative script paths against the spec's
    # own directory (desktop/), which would wrongly yield desktop/desktop/shell.py.
    [os.path.join(ROOT, "desktop", "shell.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["streamlit", "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6"],
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
