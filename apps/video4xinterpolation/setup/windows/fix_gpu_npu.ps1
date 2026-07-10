#Requires -Version 5.1
<#
  One-shot: rebuild .venv on Ryzen AI Python 3.12, install VitisAI wheels, probe EPs.
  Run inside Windows PowerShell (your existing powershell.exe session is fine):

    Set-ExecutionPolicy -Scope Process Bypass
    cd D:\Gits\MaintainAll\apps\video4xinterpolation
    .\setup\windows\fix_gpu_npu.ps1
#>
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\..\..
$ProjectRoot = (Get-Location).Path

Write-Host "=== 1) Force rebuild .venv + Ryzen AI ORT wheels ===" -ForegroundColor Cyan
& powershell -NoProfile -ExecutionPolicy Bypass -File "$ProjectRoot\setup\windows\install.ps1" -ForceVenv

Write-Host "`n=== 2) Probe EPs ===" -ForegroundColor Cyan
& powershell -NoProfile -ExecutionPolicy Bypass -File "$ProjectRoot\setup\windows\probe_ep.ps1"

Write-Host "`n=== 3) Quick ORT session smoke (DML + VitisAI if present) ===" -ForegroundColor Cyan
$env:RYZEN_AI_INSTALLATION_PATH = if ($env:RYZEN_AI_INSTALLATION_PATH) {
    $env:RYZEN_AI_INSTALLATION_PATH
} else {
    'C:\Program Files\RyzenAI\1.7.1'
}
$py = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
& $py -c @"
import os, numpy as np, onnxruntime as ort
print('providers', ort.get_available_providers())
print('RYZEN_AI', os.environ.get('RYZEN_AI_INSTALLATION_PATH'))
# Prefer listing only; full RIFE needs exported ONNX
for name in ('DmlExecutionProvider', 'VitisAIExecutionProvider', 'CPUExecutionProvider'):
    print(f'  has {name}:', name in ort.get_available_providers())
"@

Write-Host "`nIf both Dml and VitisAI are True, next:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  `$env:RYZEN_AI_INSTALLATION_PATH='C:\Program Files\RyzenAI\1.7.1'"
Write-Host "  python scripts\export_onnx.py --full"
Write-Host "  python scripts\interpolate.py <in.mp4> <out.mp4> --platform windows --backend split-pipeline"
