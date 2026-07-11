# Prefer Ryzen AI conda for video4x (VitisAI + DirectML).
# Usage:  . .\setup\windows\env.ps1
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$rai = $env:RYZEN_AI_INSTALLATION_PATH
if (-not $rai -or -not (Test-Path $rai)) {
    foreach ($c in @(
        'C:\Program Files\RyzenAI\1.7.1',
        'C:\Program Files\RyzenAI\1.7.0',
        'C:\Program Files\RyzenAI\1.6.1'
    )) {
        if (Test-Path $c) { $rai = $c; break }
    }
}
if ($rai) {
    $env:RYZEN_AI_INSTALLATION_PATH = $rai
}

$candidates = @(
    'C:\ProgramData\miniconda3\envs\ryzen-ai-1.7.1\python.exe',
    'C:\ProgramData\miniconda3\envs\ryzen-ai-1.7.0\python.exe',
    (Join-Path $env:USERPROFILE 'miniconda3\envs\ryzen-ai-1.7.1\python.exe'),
    (Join-Path $ProjectRoot '.venv\Scripts\python.exe')
)
$Video4xPython = $null
foreach ($p in $candidates) {
    if ($p -and (Test-Path $p)) { $Video4xPython = $p; break }
}
if (-not $Video4xPython) {
    Write-Host "[WARN] No ryzen-ai / .venv python found" -ForegroundColor Yellow
} else {
    Write-Host "video4x python: $Video4xPython"
    Write-Host "RYZEN_AI_INSTALLATION_PATH=$env:RYZEN_AI_INSTALLATION_PATH"
    Write-Host "Example: & `$Video4xPython -m video4x.cli.main run -i in.mp4 -o out.mp4 --ops interpolate"
}
