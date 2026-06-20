"""Shared, UI-free core for the PQA desktop/web app.

Modules here are pure Python (pandas/numpy) and carry **no** host-only
dependencies in the CSV/compliance path, so the same code runs natively in the
Windows host (PyWebview) today and, later, in Pyodide on iPad.

- ``core.analysis``      — data processing, event detection, compliance (the engine)
- ``core.viz_dataprep``  — JSON-serialisable chart series/markers shared by the
                           on-screen ECharts UI and the matplotlib report images
"""
