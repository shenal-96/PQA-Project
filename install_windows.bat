@echo off
setlocal EnableDelayedExpansion
title PQA – Windows Installer

echo.
echo  ============================================================
echo   PQA Power Quality Analysis – Windows Installer
echo  ============================================================
echo.

:: ── Verify we are in the project root ────────────────────────────────────────
if not exist "%~dp0app.py" (
    echo  [ERROR] Cannot find app.py in this folder.
    echo  Please run install_windows.bat from the PQA-Project directory.
    echo.
    pause
    exit /b 1
)

set "PROJECT_DIR=%~dp0"
:: Strip trailing backslash
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python was not found.
    echo  Download Python 3.10 or later from https://python.org
    echo  During installation tick "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.10 or later is required.
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo  Found: Python %%v
    echo  Download the latest version from https://python.org
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python !PYVER! found.

:: ── Create virtual environment ───────────────────────────────────────────────
if not exist "%PROJECT_DIR%\.venv\Scripts\activate.bat" (
    echo.
    echo  Creating virtual environment...
    python -m venv "%PROJECT_DIR%\.venv"
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
) else (
    echo  [OK] Virtual environment already exists.
)

:: ── Install Python dependencies ──────────────────────────────────────────────
echo.
echo  Installing Python dependencies (this may take a few minutes)...
call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
pip install --upgrade pip --quiet
pip install -r "%PROJECT_DIR%\requirements.txt" --quiet
if errorlevel 1 (
    echo  [ERROR] Dependency installation failed.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)
echo  [OK] Dependencies installed.

:: ── Create desktop shortcut ──────────────────────────────────────────────────
echo.
echo  Creating desktop shortcut...

set "LAUNCHER=%PROJECT_DIR%\run_pqa.bat"
set "PS_SCRIPT=%TEMP%\pqa_create_shortcut.ps1"

echo $ws = New-Object -ComObject WScript.Shell > "%PS_SCRIPT%"
echo $desktop = [Environment]::GetFolderPath('Desktop') >> "%PS_SCRIPT%"
echo $sc = $ws.CreateShortcut($desktop + '\PQA Analysis.lnk') >> "%PS_SCRIPT%"
echo $sc.TargetPath = '%LAUNCHER%' >> "%PS_SCRIPT%"
echo $sc.WorkingDirectory = '%PROJECT_DIR%' >> "%PS_SCRIPT%"
echo $sc.IconLocation = '%SystemRoot%\System32\imageres.dll,109' >> "%PS_SCRIPT%"
echo $sc.Description = 'PQA Power Quality Analysis' >> "%PS_SCRIPT%"
echo $sc.WindowStyle = 1 >> "%PS_SCRIPT%"
echo $sc.Save() >> "%PS_SCRIPT%"

powershell -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
del "%PS_SCRIPT%" >nul 2>&1

if exist "%USERPROFILE%\Desktop\PQA Analysis.lnk" (
    echo  [OK] Desktop shortcut "PQA Analysis" created.
) else (
    echo  [WARN] Could not create desktop shortcut automatically.
    echo  You can manually create a shortcut pointing to:
    echo  %LAUNCHER%
)

:: ── Done ─────────────────────────────────────────────────────────────────────
echo.
echo  ============================================================
echo   Installation complete!
echo.
echo   Double-click "PQA Analysis" on your desktop to launch.
echo   The app will open in your default browser automatically.
echo.
echo   NOTE: Do not move the PQA-Project folder after installation.
echo         If you do, run install_windows.bat again to update
echo         the desktop shortcut.
echo  ============================================================
echo.
pause
