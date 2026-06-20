# PQA web frontend

Shared UI for the **Windows desktop app** (rendered by the PyWebview/WebView2
shell) and, later, the **iPad PWA**. Svelte 5 + Vite + TypeScript + Apache ECharts.

## Dev (plain browser, no Python)

```bash
npm install
npm run dev          # http://localhost:5174
```

In a plain browser there is no PyWebview bridge, so the app falls back to
`MockBackend`, which serves committed sample data and lets you build UI without
the desktop shell. Regenerate the sample from the real engine with:

```bash
python web/scripts/gen_sample.py   # writes src/dev/sample_*.json
```

## Build (bundled into the desktop app)

```bash
npm run build        # -> web/dist/  (desktop/shell.py loads web/dist/index.html)
npm run check        # svelte-check type check
```

`vite.config.ts` uses `base: './'` so `dist/index.html` loads from a local
`file://` path with no web server.

## The backend seam (iPad-readiness)

UI components depend only on the `AnalysisBackend` interface (`src/backend/`),
never on `window.pywebview`. Implementations:

| Backend | When | How |
|---|---|---|
| `PyWebviewBackend` | Windows desktop | in-process bridge `window.pywebview.api.*` |
| `MockBackend` | browser dev | committed sample JSON |
| `PyodideBackend` | iPad (future) | Pyodide web worker — same JSON contract |

`selectBackend()` picks PyWebview when the bridge is present, else Mock.

> Note: the ECharts bundle is large; it will be code-split for the PWA build.
