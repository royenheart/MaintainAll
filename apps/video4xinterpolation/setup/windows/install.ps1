#Requires -Version 5.1
<#
.SYNOPSIS
  Windows 原生环境：检查 + 文档步骤 + 按需自动安装（已满足则跳过）

.DESCRIPTION
  目标：同一 ORT 进程内 Stage A=DirectML(GPU) + Stage B=VitisAI(NPU)。
  依赖尽量少：不装 onnxruntime-rocm；GPU/NPU EP 来自系统 WinML / Ryzen AI。

.EXAMPLE
  .\install.ps1 -CheckOnly
  .\install.ps1
  .\install.ps1 -NpuZip C:\Downloads\RAI_*.zip -RyzenAiInstaller C:\Downloads\ryzen-ai-*.exe
#>
param(
    [switch] $CheckOnly,
    [switch] $ForceGpuInstall,
    [switch] $ForceVenv,   # 强制重建 .venv（基解释器搬家/卸载后用）
    [string] $NpuZip,
    [string] $RyzenAiInstaller,
    [string] $AdrenalinSetupPath,
    [string] $PythonExe = ""   # 空 = 自动探测（py -3 / python）
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$MinGpuVersion = [version]'32.0.23027.2005'   # Adrenalin 26.2.2+
$MinNpuVersion = [version]'32.0.203.280'
$AdrenalinUrl = 'https://drivers.amd.com/drivers/whql-amd-software-adrenalin-edition-26.2.2-win11-b.exe'
$DownloadDir = Join-Path $env:USERPROFILE 'Downloads\rife-amd'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

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
                    Name   = $p.DriverDesc
                    Version = $p.DriverVersion
                    VerObj  = Convert-DriverVersion $p.DriverVersion
                }
            }
        } catch { }
    }
    return $out
}

function Test-GpuOk {
    foreach ($g in @(Get-AmdGpuDrivers)) {
        if ($g.VerObj -and $g.VerObj -ge $MinGpuVersion) { return $true }
    }
    return $false
}

function Get-NpuDevices {
    Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object {
        $_.FriendlyName -match '(?i)\bNPU\b|Compute Accelerator|XDNA'
    }
}

function Test-NpuDriverOk {
    $ok = $false
    Get-WmiObject Win32_PnPSignedDriver -ErrorAction SilentlyContinue | Where-Object {
        $_.DeviceName -match '(?i)\bNPU\b|Compute Accelerator|XDNA'
    } | ForEach-Object {
        $v = Convert-DriverVersion ([string]$_.DriverVersion)
        if ($v -and $v -ge $MinNpuVersion) { $ok = $true }
        elseif (-not $v) { $ok = $true }  # device present, version unknown
    }
    if (-not $ok -and @(Get-NpuDevices).Count -gt 0) { $ok = $true }
    return $ok
}

function Test-RyzenAiInstalled {
    return $null -ne (Get-RyzenAiRoot)
}

function Get-OrtProviders([string]$Py) {
    try {
        $out = & $Py -c "import onnxruntime as ort; print(','.join(ort.get_available_providers()))" 2>$null
        return [string]$out
    } catch { return '' }
}

function Show-RyzenAiDownloadHint {
    Write-Host ""
    Write-Host "--- Ryzen AI Software 下载提示 ---" -ForegroundColor Cyan
    Write-Host "文档: https://ryzenai.docs.amd.com/en/latest/inst.html"
    Write-Host "步骤: 打开文档中的 ryzen-ai-lt-*.exe 链接 → 登录普通 AMD 账号（非合作伙伴限定）"
    Write-Host "      → 接受 EULA → 浏览器下载 → 再运行:"
    Write-Host "      .\install.ps1 -RyzenAiInstaller C:\path\to\ryzen-ai-lt-*.exe"
    Write-Host ""
    Write-Host "出口管制 (Export Control):" -ForegroundColor Yellow
    Write-Host "  AMD Ryzen AI / 相关软件受美国出口管理条例 (EAR) 约束。"
    Write-Host "  下载与账号校验可能要求：使用美国政府允许的地址/国家信息，以及合规的网络出口 IP。"
    Write-Host "  若账号被 Export Compliance 拦截，见:"
    Write-Host "  https://www.amd.com/en/site-notifications/export-compliance.html"
    Write-Host "  本脚本不会代下安装包（无公开直链；需人工过门户）。"
    Write-Host ""
}

function Show-Docs {
    Write-Host ""
    Write-Host "=== 文档步骤（Windows 原生：DML GPU + VitisAI NPU）===" -ForegroundColor Cyan
    Write-Host "1. GPU: Adrenalin >= 26.2.2（本脚本可装；已够新则跳过；强制重装用 -ForceGpuInstall）"
    Write-Host "2. NPU: 驱动 >= 32.0.203.280（-NpuZip 指向 RAI_*_WHQL.zip）"
    Write-Host "3. Ryzen AI Software（提供 VitisAI EP / 系统 ORT 注册）"
    Write-Host "   安装后确认环境变量 RYZEN_AI_INSTALLATION_PATH"
    Write-Host "4. Python: 本脚本创建 .venv 并 pip install -e .[export,dev]"
    Write-Host "   不要装 onnxruntime-rocm；优先系统/Ryzen AI 的 ORT（含 Dml + VitisAI）"
    Write-Host "5. 推理: python scripts/interpolate.py in.mp4 out.mp4 --platform windows --backend split-pipeline"
    if (-not (Test-RyzenAiInstalled)) {
        Show-RyzenAiDownloadHint
    } else {
        Write-Host ""
    }
}

function Install-GpuIfNeeded {
    if ((Test-GpuOk) -and -not $ForceGpuInstall) {
        Write-Host "[OK]   GPU driver already sufficient (>= $MinGpuVersion). Skip."
        return
    }
    if (-not (Test-Admin)) { throw "Install GPU requires Administrator." }
    New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null
    $dest = if ($AdrenalinSetupPath) { $AdrenalinSetupPath } else { Join-Path $DownloadDir 'adrenalin-26.2.2-win11-b.exe' }
    if (-not (Test-Path $dest)) {
        Write-Host "Downloading Adrenalin 26.2.2..."
        Invoke-WebRequest -Uri $AdrenalinUrl -OutFile $dest -UseBasicParsing -Headers @{
            Referer = 'https://www.amd.com/'
            'User-Agent' = 'Mozilla/5.0'
        }
    }
    $log = Join-Path $DownloadDir 'adrenalin-install.log'
    $proc = Start-Process -FilePath $dest -ArgumentList @('-INSTALL', '-view:3', '-LOG', $log) -Wait -PassThru
    if ($proc.ExitCode -notin 0, 2) { throw "Adrenalin installer exit $($proc.ExitCode). See $log" }
    Write-Host "[OK]   Adrenalin install finished (exit $($proc.ExitCode))."
}

function Install-NpuIfNeeded {
    if ((Test-NpuDriverOk) -and -not $NpuZip) {
        Write-Host "[OK]   NPU device/driver present. Skip NPU install."
        return
    }
    if (-not $NpuZip) {
        Write-Host "[WARN] NPU not OK and -NpuZip not set. Install manually (see docs)." -ForegroundColor Yellow
        return
    }
    if (-not (Test-Admin)) { throw "NPU install requires Administrator." }
    $zip = Resolve-Path $NpuZip
    $dest = Join-Path $env:TEMP 'rife-npu'
    Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -Path $zip -DestinationPath $dest -Force
    $exe = Get-ChildItem $dest -Recurse -Filter 'npu_sw_installer.exe' | Select-Object -First 1
    if (-not $exe) { throw "npu_sw_installer.exe not found in zip" }
    $proc = Start-Process -FilePath $exe.FullName -WorkingDirectory $exe.DirectoryName -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "NPU installer exit $($proc.ExitCode)" }
    Write-Host "[OK]   NPU driver installed."
}

function Install-RyzenAiIfNeeded {
    if (Test-RyzenAiInstalled) {
        Write-Host "[OK]   Ryzen AI Software already installed. Skip."
        return
    }
    if (-not $RyzenAiInstaller) {
        Write-Host "[WARN] Ryzen AI Software not installed; installer path not given." -ForegroundColor Yellow
        Show-RyzenAiDownloadHint
        return
    }
    if (-not (Test-Admin)) { throw "Ryzen AI install requires Administrator." }
    $setup = Resolve-Path $RyzenAiInstaller
    Write-Host "Running Ryzen AI installer (GUI/EULA may appear)..."
    $proc = Start-Process -FilePath $setup -Wait -PassThru
    Write-Host "[OK]   Ryzen AI installer exit $($proc.ExitCode)."
}

function Get-RyzenAiRoot {
    $candidates = @(
        $env:RYZEN_AI_INSTALLATION_PATH,
        [Environment]::GetEnvironmentVariable('RYZEN_AI_INSTALLATION_PATH', 'Machine'),
        [Environment]::GetEnvironmentVariable('RYZEN_AI_INSTALLATION_PATH', 'User'),
        'C:\Program Files\RyzenAI\1.7.1',
        'C:\Program Files\RyzenAI\1.7.0',
        'C:\Program Files\RyzenAI\1.6.1'
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    $base = 'C:\Program Files\RyzenAI'
    if (Test-Path $base) {
        $latest = Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -First 1
        if ($latest) { return $latest.FullName }
    }
    return $null
}

function Get-RyzenAiCondaPython {
    $roots = @(
        'C:\ProgramData\miniconda3',
        'C:\ProgramData\miniforge3',
        "$env:USERPROFILE\miniconda3",
        "$env:USERPROFILE\miniforge3",
        "$env:USERPROFILE\Miniforge3",
        "$env:USERPROFILE\anaconda3",
        "$env:LOCALAPPDATA\miniforge3"
    )
    foreach ($r in $roots) {
        foreach ($envName in @('ryzen-ai-1.7.1', 'ryzen-ai-1.7.0', 'ryzen-ai-1.6.1')) {
            $p = Join-Path $r "envs\$envName\python.exe"
            if (Test-Path $p) { return $p }
        }
    }
    return $null
}

function Get-PythonVersionTag([string]$Py) {
    try {
        $out = & $Py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0) { return [string]($out | Select-Object -First 1).Trim() }
    } catch { }
    return ''
}

function Resolve-BasePython {
    # Prefer: -PythonExe → Ryzen AI conda (3.12) → py -3.12 → other py → PATH python.
    if ($PythonExe) {
        if (Test-Path $PythonExe) { return (Resolve-Path $PythonExe).Path }
        $cmd = Get-Command $PythonExe -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        throw "Python not found ($PythonExe). Pass -PythonExe with a real path."
    }
    $raiPy = Get-RyzenAiCondaPython
    if ($raiPy) {
        Write-Host "[INFO] Prefer Ryzen AI conda Python for VitisAI EP: $raiPy"
        return $raiPy
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($ver in @('-3.12', '-3.11', '-3.10', '-3.13', '-3')) {
            try {
                $out = & py $ver -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $out -and (Test-Path ($out | Select-Object -First 1))) {
                    return [string]($out | Select-Object -First 1)
                }
            } catch { }
        }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and (Test-Path $cmd.Source)) { return $cmd.Source }
    throw "Python 3.10+ not found. For VitisAI use Python 3.12 (Ryzen AI conda) or pass -PythonExe."
}

function Test-VenvHealthy {
    if (-not (Test-Path $VenvPython)) { return $false }
    $cfg = Join-Path $ProjectRoot '.venv\pyvenv.cfg'
    if (Test-Path $cfg) {
        $homeLine = Get-Content $cfg | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
        if ($homeLine) {
            # Do not use $HOME — it is a read-only automatic variable in PowerShell.
            $venvHome = ($homeLine -replace '^\s*home\s*=\s*', '').Trim()
            $basePy = Join-Path $venvHome 'python.exe'
            if (-not (Test-Path $basePy)) {
                Write-Host "[WARN] .venv base interpreter missing: $basePy" -ForegroundColor Yellow
                return $false
            }
        }
    }
    try {
        $null = & $VenvPython -c "import sys; print(sys.version)" 2>&1
        if ($LASTEXITCODE -ne 0) { return $false }
    } catch {
        return $false
    }
    # Ryzen AI 1.7.1 wheels are cp312-only; a 3.14 venv can never see VitisAI.
    if ((Get-RyzenAiRoot) -and (Get-PythonVersionTag $VenvPython) -ne '3.12') {
        Write-Host "[WARN] .venv is Python $(Get-PythonVersionTag $VenvPython); Ryzen AI VitisAI wheels need 3.12." -ForegroundColor Yellow
        Write-Host "       Re-run with -ForceVenv (script will prefer ryzen-ai-1.7.1 / py -3.12)." -ForegroundColor Yellow
        return $false
    }
    return $true
}

function Install-RyzenAiOrtWheels {
    param([string]$Py)
    $root = Get-RyzenAiRoot
    if (-not $root) { return $false }
    $tag = Get-PythonVersionTag $Py
    if ($tag -ne '3.12') {
        Write-Host "[WARN] Cannot install Ryzen AI ORT wheels on Python $tag (need 3.12)." -ForegroundColor Yellow
        return $false
    }
    $voe = Get-ChildItem $root -Filter 'voe-*-py3-none-win_amd64.whl' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    $ort = Get-ChildItem $root -Filter 'onnxruntime_vitisai-*-cp312-cp312-win_amd64.whl' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $voe -or -not $ort) {
        Write-Host "[WARN] voe / onnxruntime_vitisai wheels not found under $root" -ForegroundColor Yellow
        return $false
    }
    Write-Host "Installing Ryzen AI ORT (VitisAI + typically DirectML) from:"
    Write-Host "  $($voe.FullName)"
    Write-Host "  $($ort.FullName)"
    # pip writes WARNINGs to stderr; with $ErrorActionPreference=Stop that becomes NativeCommandError.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Py -m pip uninstall -y onnxruntime onnxruntime-directml onnxruntime-gpu 2>&1 | Out-Null
    & $Py -m pip install --force-reinstall --no-deps $voe.FullName $ort.FullName -q
    # onnxruntime_vitisai 1.23.x is built against NumPy 1.x; wheel omits coloredlogs meta-dep.
    & $Py -m pip install "numpy>=1.24,<2" coloredlogs -q
    $ErrorActionPreference = $prevEap
    if (-not $env:RYZEN_AI_INSTALLATION_PATH) {
        $env:RYZEN_AI_INSTALLATION_PATH = $root
        Write-Host "[OK]   Set process RYZEN_AI_INSTALLATION_PATH=$root"
    }
    return $true
}

function Install-PythonEnv {
    $py = Resolve-BasePython
    Write-Host "[OK]   Base Python: $py (version $(Get-PythonVersionTag $py))"

    $venvDir = Join-Path $ProjectRoot '.venv'
    $needCreate = $ForceVenv -or -not (Test-VenvHealthy)
    if ($needCreate) {
        if (Test-Path $venvDir) {
            Write-Host "Removing broken/stale .venv (base python moved, wrong version, or -ForceVenv)..."
            Remove-Item -LiteralPath $venvDir -Recurse -Force
        }
        Write-Host "Creating venv at $venvDir"
        & $py -m venv $venvDir
        if (-not (Test-Path $VenvPython)) {
            throw "venv created but python missing at $VenvPython"
        }
    } else {
        Write-Host "[OK]   .venv healthy. Skip create."
    }

    & $VenvPython -m pip install --upgrade pip wheel -q
    & $VenvPython -m pip install -e "$ProjectRoot[export,dev]" -q

    $prov = Get-OrtProviders $VenvPython
    $raiRoot = Get-RyzenAiRoot

    if ($raiRoot -and ($prov -notmatch 'VitisAI')) {
        if (Install-RyzenAiOrtWheels -Py $VenvPython) {
            $prov = Get-OrtProviders $VenvPython
        }
    }

    if (-not $prov) {
        Write-Host "Installing onnxruntime (CPU baseline)..."
        & $VenvPython -m pip install "onnxruntime>=1.17" -q
        $prov = Get-OrtProviders $VenvPython
    }

    if ($prov -notmatch 'Dml' -and $prov -notmatch 'VitisAI') {
        Write-Host "DmlExecutionProvider missing — installing onnxruntime-directml for Stage A (GPU)..."
        & $VenvPython -m pip uninstall -y onnxruntime 2>$null
        & $VenvPython -m pip install "onnxruntime-directml>=1.17" -q
        $prov = Get-OrtProviders $VenvPython
    }

    if ($prov) {
        Write-Host "[OK]   onnxruntime providers: $prov"
    } else {
        Write-Host "[WARN] onnxruntime still not importable" -ForegroundColor Yellow
    }

    if ($prov -notmatch 'VitisAI') {
        Write-Host "[WARN] VitisAI EP still missing — Stage B stays CPU." -ForegroundColor Yellow
        Write-Host "       Ryzen AI puts EP in conda env ryzen-ai-1.7.1 (Python 3.12), not a 3.14 .venv."
        Write-Host "       Fix: .\install.ps1 -ForceVenv"
        Write-Host "       Or:  conda activate ryzen-ai-1.7.1 ; pip install -e .[export,dev]"
        Show-RyzenAiDownloadHint
    } else {
        Write-Host "[OK]   VitisAI EP present — Stage B can use NPU (quant model + xclbin)."
    }
    if ($prov -match 'Dml') {
        Write-Host "[OK]   DirectML present — Stage A can use GPU."
    }
}

function Invoke-Check {
    Write-Host "`n=== Windows native check ===" -ForegroundColor Cyan
    $os = Get-CimInstance Win32_OperatingSystem
    Write-Host "[OK]   $($os.Caption) build $($os.BuildNumber)"

    $gpus = @(Get-AmdGpuDrivers)
    if ($gpus.Count -eq 0) {
        Write-Host "[FAIL] No AMD GPU driver" -ForegroundColor Red
    } else {
        foreach ($g in $gpus) {
            if ($g.VerObj -ge $MinGpuVersion) {
                Write-Host "[OK]   $($g.Name) v$($g.Version) (DirectML OK)"
            } else {
                Write-Host "[WARN] $($g.Name) v$($g.Version) — need >= $MinGpuVersion" -ForegroundColor Yellow
            }
        }
    }

    $npus = @(Get-NpuDevices)
    if ($npus.Count -eq 0) {
        Write-Host "[WARN] No NPU PnP device" -ForegroundColor Yellow
    } else {
        $npus | ForEach-Object { Write-Host "[OK]   NPU: $($_.FriendlyName) ($($_.Status))" }
    }

    if (Test-RyzenAiInstalled) {
        Write-Host "[OK]   Ryzen AI path: $(Get-RyzenAiRoot)"
        $condaPy = Get-RyzenAiCondaPython
        if ($condaPy) {
            $cp = Get-OrtProviders $condaPy
            Write-Host "[OK]   conda ryzen-ai ORT providers: $cp"
        }
    } else {
        Write-Host "[WARN] Ryzen AI Software not detected (needed for VitisAI EP)" -ForegroundColor Yellow
    }

    if (Test-Path $VenvPython) {
        Write-Host "[INFO] .venv Python $(Get-PythonVersionTag $VenvPython)"
        $prov = Get-OrtProviders $VenvPython
        if ($prov) {
            Write-Host "[OK]   .venv ORT providers: $prov"
            if ($prov -notmatch 'Dml') { Write-Host "[WARN] DmlExecutionProvider missing — Stage A may be CPU" -ForegroundColor Yellow }
            if ($prov -notmatch 'VitisAI') {
                Write-Host "[WARN] VitisAIExecutionProvider missing — Stage B may be CPU" -ForegroundColor Yellow
                Write-Host "       Cause: .venv is not the Ryzen AI Python 3.12 ORT. Run: .\install.ps1 -ForceVenv" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[WARN] Cannot import onnxruntime in .venv" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[INFO] .venv not created yet"
    }

    Show-Docs
    Write-Host "Next: .\install.ps1   (or -CheckOnly). Then:"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  python scripts\interpolate.py in.mp4 out.mp4 --platform windows --backend split-pipeline"
}

# --- main ---
Show-Docs

if (-not $CheckOnly) {
    Install-GpuIfNeeded
    Install-NpuIfNeeded
    Install-RyzenAiIfNeeded
    Install-PythonEnv
}

Invoke-Check
