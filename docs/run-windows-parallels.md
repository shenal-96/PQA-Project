# Running the PQA desktop app in Parallels (Apple Silicon → Windows 11 ARM)

Your Mac is Apple Silicon, so Parallels runs **Windows 11 on ARM**. Two ways to
test:

- **A. Run from source** (fastest dev loop). Uses native ARM Python — no
  emulation. Best for iterating on the Compliance workflow.
- **B. Download the x86-64 build** from GitHub Actions and run it under Windows'
  built-in emulation. Best for testing the *packaged* app exactly as it ships.

WebView2 (the Chromium engine the app embeds) is **preinstalled on Windows 11**,
so nothing extra is needed there.

---

## A. Run from source (recommended for dev)

In the Windows 11 VM:

1. **Install Python 3.11** — https://www.python.org/downloads/windows/ (the
   "Windows installer (ARM64)" is fine). Tick *Add python.exe to PATH*.
2. **Install Node 22** — https://nodejs.org (LTS).
3. **Get the code** (Git for Windows, or copy the folder from the Mac via a
   Parallels shared folder), then in a terminal at the repo root:

   ```powershell
   # build the single-file web UI
   cd web
   npm install
   npm run build
   cd ..

   # install the runtime deps and launch the app
   py -3.11 -m pip install pandas "numpy>=1.24" pywebview
   py -3.11 -m desktop.shell
   ```

   > Note: the Compliance (CSV) workflow needs only `pandas numpy pywebview`.
   > `python-calamine` (XLS tabs) ships a Windows **x64** wheel; on ARM Python it
   > may try to build from source. Skip it for now — it isn't needed for the
   > current Compliance build. We'll handle the XLS tabs when those land.

4. **What you should see:** a native window titled *"PQA — Power Quality
   Analysis"*. Click **Load CSV**, pick `tests/fixtures/hioki_sample.csv`, and you
   should get an interactive voltage chart, the metric cards (2 events, both
   Pass), and the compliance table. This is the real engine running in-process —
   no server.

---

## B. Download and run the x86-64 build

1. On GitHub: **Actions → package-windows → Run workflow** (branch
   `claude/bold-pasteur-zoi0gk`). When it finishes, download the
   **`PQA-windows-x64`** artifact.
2. Copy the unzipped `PQA` folder into the Windows VM and run **`PQA.exe`**.
   Windows-on-ARM transparently emulates the x64 binary.
3. A console window will appear alongside the app window (we left `console=True`
   in the build so first-run errors are visible). Same UI/flow as above.

If `PQA.exe` shows an error in the console, copy it back to me — that's exactly
the kind of packaging issue I can fix from the CI logs.

---

## Why x64 for an ARM Mac?

The product ships as an **x86-64** Windows app, and a true x64 build must be
produced on x64 Windows. GitHub Actions' `windows-latest` runners are x64, so CI
builds and tests the real target there. The resulting x64 `.exe` still runs in
your ARM VM via emulation, so you can validate the actual shipping artifact on
your Mac.
