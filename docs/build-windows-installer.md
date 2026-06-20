# Building the PQA Windows installer

The desktop app ships as a single **Setup .exe** produced by [Inno Setup](https://jrsoftware.org/isinfo.php)
that wraps the PyInstaller onedir build and provisions the runtime the embedded
WebView2 UI needs.

> The legacy Streamlit app is **not** part of this — it keeps running via
> `streamlit run app.py` and is unaffected by anything here.

## What the installer does

1. Installs the PyInstaller payload (`PQA.exe` + `_internal\`, including the
   bundled single-file web UI, `python_calamine`, `matplotlib`, `python-docx`)
   into `Program Files\PQA`.
2. Provisions the **WebView2 Evergreen Runtime** — downloads Microsoft's
   Evergreen Bootstrapper and installs it silently **only if** it is not already
   present (it ships with Windows 11; may be missing on older Windows 10).
3. Verifies **.NET Framework 4.8** is present. The app forces
   `PYTHONNET_RUNTIME=netfx` (`desktop/shell.py`), so pythonnet/WinForms use the
   .NET **Framework** that is built into Windows 10 1903+/11 — the modern .NET
   Desktop Runtime is **not** required. The installer only warns if 4.8 is
   somehow absent.
4. Creates Start-menu (and optional desktop) shortcuts and a clean uninstaller.

## Local build (Windows)

```bat
:: 1. Build the single-file web UI
cd web && npm ci && npm run build && cd ..

:: 2. Build the desktop app (onedir → dist\PQA)
pip install -r desktop\requirements.txt
pyinstaller desktop\pqa.spec --noconfirm

:: 3. Compile the installer (needs Inno Setup 6.1+)
iscc desktop\installer.iss
```

Output: `desktop\Output\PQA-Setup-<version>.exe`.

Override the payload location if needed:
`iscc /DAppDir=path\to\PQA desktop\installer.iss`.

## CI

`.github/workflows/package-windows.yml` builds both artifacts on every push that
touches `desktop/`, `core/`, or `web/`:

- **PQA-windows-x64** — the raw onedir folder (`dist\PQA`).
- **PQA-windows-installer** — the compiled `PQA-Setup-*.exe`.

Inno Setup is installed in CI via `choco install innosetup`, so a broken
`installer.iss` fails the build — the script is compile-verified on every push.
Download either artifact from the latest green run.

## Notes / TODO (M5 remainder, gated on parity sign-off)

These are intentionally **deferred** so the live Streamlit app stays untouched:

- Telemetry env-var config for the desktop (`tracking._get_secret` → env) — the
  shared `tracking.py` is left as-is for now.
- Removing `packages.txt` / legacy PDF deps and retiring `app.py` — only after
  the desktop build is signed off against the Streamlit app.
- Flip `console=True` → `False` in `desktop/pqa.spec` once first-run tracebacks
  are no longer needed.
- Code-signing the installer + exe (requires a certificate).
