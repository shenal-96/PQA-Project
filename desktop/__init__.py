"""Windows desktop host for the PQA app (PyWebview + WebView2).

Runs entirely on the local machine: the UI is local files rendered in an
embedded Chromium control, and JS<->Python is an in-process bridge — no web
server, no network. See ``desktop/shell.py``.
"""
