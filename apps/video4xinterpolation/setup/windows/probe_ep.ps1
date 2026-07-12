#Requires -Version 5.1
<#
  Probe DirectML + VitisAI in project .venv and Ryzen AI conda env.
  Run in Windows PowerShell (not WSL):
    powershell -ExecutionPolicy Bypass -File setup\windows\probe_ep.ps1
#>
$ErrorActionPreference = 'Continue'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$RaiRoot = if ($env:RYZEN_AI_INSTALLATION_PATH) { $env:RYZEN_AI_INSTALLATION_PATH } else { 'C:\Program Files\RyzenAI\1.7.1' }
if (-not $env:RYZEN_AI_INSTALLATION_PATH -and (Test-Path $RaiRoot)) {
    $env:RYZEN_AI_INSTALLATION_PATH = $RaiRoot
}

function Show-Providers([string]$Label, [string]$Py) {
    Write-Host "`n=== $Label ===" -ForegroundColor Cyan
    Write-Host "python: $Py"
    if (-not (Test-Path $Py)) { Write-Host "[FAIL] missing"; return }
    & $Py -c @"
import os, sys
print('version', sys.version)
print('RYZEN_AI_INSTALLATION_PATH', os.environ.get('RYZEN_AI_INSTALLATION_PATH'))
import onnxruntime as ort
print('ort', ort.__version__, ort.__file__)
print('providers', ort.get_available_providers())
"@
}

Show-Providers 'project .venv' $VenvPython
Show-Providers 'conda ryzen-ai-1.7.1' 'C:\ProgramData\miniconda3\envs\ryzen-ai-1.7.1\python.exe'

Write-Host "`nNext (GPU+NPU):" -ForegroundColor Cyan
Write-Host "  1) .\install.ps1 -ForceVenv   # rebuild .venv on Python 3.12 + install RAI wheels"
Write-Host "  OR conda activate ryzen-ai-1.7.1"
Write-Host "     pip install -e `"$ProjectRoot[export,dev]`""
Write-Host "  2) `$env:RYZEN_AI_INSTALLATION_PATH='$RaiRoot'"
Write-Host "  3) python scripts\export_onnx.py --full"
Write-Host "  4) python scripts\interpolate.py in.mp4 out.mp4 --platform windows --backend split-pipeline"
