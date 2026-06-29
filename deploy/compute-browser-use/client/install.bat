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
echo [*] Checking cua-driver...
powershell -NoProfile -Command "$d='%LOCALAPPDATA%\Programs\Cua\cua-driver\bin\cua-driver.exe'; $h='%USERPROFILE%\.cua-driver\packages\current\cua-driver.exe'; if ((Test-Path $d) -or (Test-Path $h) -or (Get-Command cua-driver -ErrorAction SilentlyContinue)) { Write-Host '  cua-driver already installed'; exit 0 } else { exit 1 }"
if %errorlevel% equ 0 goto :cua_driver_done
echo.
echo [*] Installing cua-driver (background automation)...
echo     Downloading installer from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $script=irm https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.ps1; $tmp=\"%TEMP%\install-cua-driver.ps1\"; [IO.File]::WriteAllText($tmp,$script); & powershell -NoProfile -ExecutionPolicy Bypass -File $tmp -NoAutoStart; Remove-Item $tmp -ErrorAction SilentlyContinue"
:cua_driver_done

echo.
echo [2/4] Creating startup shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([Environment]::GetFolderPath('Startup') + '\CUA-Control-Plane.lnk'); $sc.TargetPath = 'python.exe'; $sc.Arguments = '-m cua_control_plane.main'; $sc.WorkingDirectory = '%~dp0'; $sc.Save()"
echo Startup shortcut created.

echo.
echo [3/4] Initial configuration...
python -c "from cua_control_plane.config import ControlPlaneConfig; ControlPlaneConfig().save()"
echo Default config saved to %%APPDATA%%\cua-control-plane\config.json

echo.
echo [4/4] Starting CUA Control Plane...
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; try { $r = Invoke-WebRequest 'http://127.0.0.1:9111/health' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { Write-Host 'Previous instance found. Restarting...'; $conns = netstat -ano | Select-String ':9111.*LISTENING'; foreach ($c in $conns) { $p = ($c -split '\s+' | Where-Object {$_})[-1]; Stop-Process -Id $p -Force }; Start-Sleep 2 } } catch {}; exit 0"
powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -Command "Start-Process python -ArgumentList '-m','cua_control_plane.main' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
echo CUA Control Plane started.

:install_done
echo.
echo ============================================
echo  Installation complete!
echo.
echo  Check the system tray (near the clock)
echo  for the CUA Control Plane icon.
echo.
echo  Local API: http://127.0.0.1:9111
echo  Health:    http://127.0.0.1:9111/health
echo  Test UI:   http://127.0.0.1:9111/tests
echo ============================================
pause
