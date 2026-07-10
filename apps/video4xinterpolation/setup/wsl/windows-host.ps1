#Requires -Version 5.1
<#
  WSL 透传前置：Windows 主机侧 GPU/NPU 驱动检查与按需安装。
  目标是让 WSL 里的 ROCDXG 能用到 /dev/dxg（不是 Windows 原生 DML/VitisAI 推理）。

  .\windows-host.ps1              只读检查（含 WSL /dev/dxg、rocminfo）
  .\windows-host.ps1 -InstallGpu  管理员：仅在驱动过旧时装 Adrenalin，然后 wsl --shutdown
  .\windows-host.ps1 -NpuZip C:\Downloads\RAI_*.zip
#>
param(
    [switch] $InstallGpu,
    [string] $NpuZip,
    [switch] $ForceGpuInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$MinGpuForWsl = [version]'32.0.23027.2005'
$AdrenalinUrl = 'https://drivers.amd.com/drivers/whql-amd-software-adrenalin-edition-26.2.2-win11-b.exe'
$DownloadDir = Join-Path $env:USERPROFILE 'Downloads\rife-amd'

function Test-Admin {
    $p = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Convert-DriverVersion([string]$Raw) {
    if ([string]::IsNullOrWhiteSpace($Raw)) { return $null }
    try { return [version]($Raw -replace '[^0-9\.]', '') } catch { return $null }
}

function Get-AmdGpuDrivers {
    $base = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
    if (-not (Test-Path $base)) { return @() }
    $out = @()
    Get-ChildItem $base -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $p = Get-ItemProperty $_.PSPath -ErrorAction Stop
            if ($p.DriverDesc -match 'AMD|Radeon') {
                $out += [PSCustomObject]@{
                    Name    = $p.DriverDesc
                    Version = $p.DriverVersion
                    VerObj  = Convert-DriverVersion $p.DriverVersion
                }
            }
        } catch { }
    }
    return $out
}

function Test-GpuDriverSufficient {
    $gpus = @(Get-AmdGpuDrivers)
    if ($gpus.Length -eq 0) { return $false }
    foreach ($g in $gpus) {
        if ($g.VerObj -and $g.VerObj -ge $MinGpuForWsl) { return $true }
    }
    return $false
}

function Get-NewestGpuDriver {
    $best = $null
    foreach ($g in @(Get-AmdGpuDrivers)) {
        if ($g.VerObj -and (-not $best -or $g.VerObj -gt $best.VerObj)) { $best = $g }
    }
    return $best
}

function Restart-Wsl {
    if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
        & wsl.exe --shutdown 2>&1 | Out-Null
        Write-Host "[OK]   wsl --shutdown"
    }
}

function Read-InstallerLogTail {
    param([string]$LogPath, [int]$Lines = 30)
    if (-not (Test-Path $LogPath)) { return "(no log at $LogPath)" }
    return (Get-Content $LogPath -Tail $Lines -ErrorAction SilentlyContinue) -join "`n"
}

function Install-GpuDriver {
    if (-not (Test-Admin)) { throw "Run PowerShell as Administrator." }

    $current = Get-NewestGpuDriver
    if ((Test-GpuDriverSufficient) -and -not $ForceGpuInstall) {
        Write-Host "[OK]   GPU driver already OK for WSL ROCDXG: $($current.Name) v$($current.Version)"
        Write-Host "       (>= $MinGpuForWsl / Adrenalin 26.2.2). Skipping installer."
        Write-Host "       Use -ForceGpuInstall only if you must reinstall/downgrade."
        Restart-Wsl
        return
    }

    if ($current -and $current.VerObj -and $current.VerObj -ge $MinGpuForWsl -and -not $ForceGpuInstall) {
        Write-Host "[OK]   Current driver v$($current.Version) already meets WSL minimum."
        Restart-Wsl
        return
    }

    New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null
    $dest = Join-Path $DownloadDir 'adrenalin-26.2.2-win11-b.exe'
    $log = Join-Path $DownloadDir 'adrenalin-install.log'

    if (-not (Test-Path $dest)) {
        Write-Host "Downloading Adrenalin 26.2.2 (RDNA3/4)..."
        Invoke-WebRequest -Uri $AdrenalinUrl -OutFile $dest -UseBasicParsing -Headers @{
            Referer      = 'https://www.amd.com/'
            'User-Agent' = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        }
    }

    Write-Host "Installing (driver only, silent)..."
    Write-Host "  Log: $log"
    if (Test-Path $log) { Remove-Item $log -Force -ErrorAction SilentlyContinue }

    $installArgs = @('-INSTALL', '-view:3', '-LOG', $log)
    $proc = Start-Process -FilePath $dest -ArgumentList $installArgs -Wait -PassThru

    if ($proc.ExitCode -eq 0) {
        Write-Host "[OK]   Adrenalin installed."
        Restart-Wsl
        return
    }

    if ($proc.ExitCode -eq 2) {
        Write-Host "[WARN] Install needs reboot (exit 2). Reboot, then re-run this script." -ForegroundColor Yellow
        return
    }

    $tail = Read-InstallerLogTail -LogPath $log
    $hint = @"
Installer exit $($proc.ExitCode).

Common causes:
  - Driver already newer than 26.2.2 (downgrade blocked). Re-run without -InstallGpu if version >= $MinGpuForWsl.
  - Pending reboot from a previous driver install.
  - OEM/laptop blocks reference driver install.

If driver version is already >= $MinGpuForWsl, skip Windows install and run in WSL:
  cd setup/wsl && sudo ./install.sh

Manual install: double-click $dest (Custom -> Driver Only).

Log tail:
$tail
"@
    throw $hint
}

function Install-Npu {
    param([string]$ZipPath)
    if (-not (Test-Admin)) { throw "Run PowerShell as Administrator." }
    $zip = Resolve-Path $ZipPath -ErrorAction Stop
    $dest = Join-Path $env:TEMP 'rife-npu'
    Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -Path $zip -DestinationPath $dest -Force
    $exe = Get-ChildItem $dest -Recurse -Filter 'npu_sw_installer.exe' | Select-Object -First 1
    if (-not $exe) { throw "npu_sw_installer.exe not found in zip" }
    $proc = Start-Process -FilePath $exe.FullName -WorkingDirectory $exe.DirectoryName -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "NPU installer exit $($proc.ExitCode)" }
    Write-Host "[OK]   NPU driver installed."
}

function Test-Host {
    Write-Host "`n=== Windows host (for WSL ROCDXG) ===" -ForegroundColor Cyan
    $os = Get-CimInstance Win32_OperatingSystem
    Write-Host "[OK]   $($os.Caption) build $($os.BuildNumber)"

    $gpus = @(Get-AmdGpuDrivers)
    if ($gpus.Length -eq 0) {
        Write-Host "[FAIL] No AMD GPU driver — run: .\windows-host.ps1 -InstallGpu" -ForegroundColor Red
        return 1
    }
    foreach ($g in $gpus) {
        if ($g.VerObj -and $g.VerObj -ge $MinGpuForWsl) {
            Write-Host "[OK]   $($g.Name) v$($g.Version) (WSL ROCDXG OK)"
        } else {
            Write-Host "[WARN] $($g.Name) v$($g.Version) — need >= $MinGpuForWsl" -ForegroundColor Yellow
        }
    }

    if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
        Write-Host "[OK]   wsl.exe"
        try {
            $p = & wsl.exe -e bash -lc 'test -e /dev/dxg && echo DXG_OK; rocminfo 2>/dev/null | grep -c "Device Type:.*GPU" || true' 2>&1
            if ("$p" -match 'DXG_OK') { Write-Host "[OK]   WSL /dev/dxg" }
            if ("$p" -match '^[1-9]') { Write-Host "[OK]   WSL rocminfo GPU agent" }
            elseif ("$p" -match 'DXG_OK') {
                Write-Host "[WARN] WSL: no GPU agent yet — run: sudo bash setup/wsl/install.sh" -ForegroundColor Yellow
            }
        } catch { }
    }

    Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object {
        $_.FriendlyName -match '(?i)\bNPU\b|Compute Accelerator|XDNA'
    } | ForEach-Object { Write-Host "[OK]   NPU: $($_.FriendlyName)" }

    Write-Host "`nNext (WSL): cd setup/wsl && sudo ./install.sh && source ../../.venv/bin/activate && source rocm-wsl.env"
    Write-Host "Windows native inference uses a different script: setup\windows\install.ps1"
    return 0
}

if ($InstallGpu) { Install-GpuDriver }
if ($NpuZip)     { Install-Npu -ZipPath $NpuZip }

exit (Test-Host)
