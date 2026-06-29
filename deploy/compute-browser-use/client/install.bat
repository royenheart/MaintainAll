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
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d='%LOCALAPPDATA%\Programs\Cua\cua-driver\bin\cua-driver.exe';" ^
  "$h='%USERPROFILE%\.cua-driver\packages\current\cua-driver.exe';" ^
  "if ((Test-Path $d) -or (Test-Path $h) -or (Get-Command cua-driver -ea 0)) {" ^
  "  Write-Host '  cua-driver already installed'" ^
  "} else {" ^
  "  Write-Host '  Installing cua-driver from GitHub...';" ^
  "  $ProgressPreference='SilentlyContinue';" ^
  "  $s=irm https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.ps1;" ^
  "  $t=\"$env:TEMP\install-cua-driver.ps1\";" ^
  "  [IO.File]::WriteAllText($t,$s);" ^
  "  & powershell -NoProfile -ExecutionPolicy Bypass -File $t -NoAutoStart;" ^
  "  Remove-Item $t -ErrorAction SilentlyContinue" ^
  "}"

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
echo.
echo  === Tips for best experience ===
echo.
echo  [UIAccess] Right-click tray icon -
echo             "Enable UIAccess" to grant admin elevation.
echo             This enables clean foreground swap for
echo             Chrome / VSCode clicks.
echo.
echo  [VSCode / Chrome]
echo    In collaborative mode, Chromium-based apps (VSCode,
echo    Chrome, Edge) may briefly grab focus during clicks.
echo    This is a known limitation — the UIAccess foreground
echo    swap is the best available option without deeper
echo    OS-level hooks.
echo    Workaround: switch to Solo mode via tray menu for
echo    predictable full-control behavior.
echo.
echo  [Tray]    Switch mode via tray menu:
echo             Collaborative = non-intrusive (default)
echo             Solo = full control with idle detection
echo ============================================
pause
