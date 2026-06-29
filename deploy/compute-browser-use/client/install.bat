@echo off
setlocal enabledelayedexpansion
echo ============================================
echo  CUA Control Plane - Windows Installer
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.12+ from https://python.org
    pause
    exit /b 1
)

echo [1/4] Installing Python dependencies...
pip install -r "%~dp0requirements.txt"
if %errorlevel% neq 0 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)

echo.
echo [2/4] Creating startup shortcut...
set "PSFILE=%TEMP%\cua_create_shortcut.ps1"
(
echo $ws = New-Object -ComObject WScript.Shell
echo $sc = $ws.CreateShortcut([Environment]::GetFolderPath('Startup') + '\CUA-Control-Plane.lnk')
echo $sc.TargetPath = 'pythonw.exe'
echo $sc.Arguments = '-m cua_control_plane.main'
echo $sc.WorkingDirectory = '%~dp0'
echo $sc.Save()
) > "%PSFILE%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PSFILE%"
del "%PSFILE%"
echo Startup shortcut created.

echo.
echo [3/4] Initial configuration...
python -c "from cua_control_plane.config import ControlPlaneConfig; ControlPlaneConfig().save()"
echo Default config saved to %%APPDATA%%\cua-control-plane\config.json

echo.
echo [4/4] Starting CUA Control Plane...
start "" pythonw -m cua_control_plane.main

echo.
echo ============================================
echo  Installation complete!
echo.
echo  Check the system tray (near the clock)
echo  for the CUA Control Plane icon.
echo.
echo  Local API: http://127.0.0.1:9110
echo  Health:    http://127.0.0.1:9110/health
echo ============================================
pause
