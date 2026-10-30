# Fresh Windows machine: venv + dependencies + agents + doctor.  Usage: powershell -File scripts\setup.ps1 [-Youtube]
param([switch]$Youtube)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\python -m pip install -q -r requirements.txt
if ($Youtube) { & .\.venv\Scripts\python -m pip install -q -r requirements-youtube.txt }
New-Item -ItemType Directory -Force secrets | Out-Null
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Warning "ffmpeg not found (install it for video output)" }
& .\.venv\Scripts\python -m core render-agents
& .\.venv\Scripts\python -m core list-channels
& .\.venv\Scripts\python -m core doctor
Write-Host 'Next: python -m core new-channel <slug>   or   python -m core start-script --channel example-story "an idea"'
