# One-command setup + run (Windows PowerShell). Requires Python 3.10 as py -3.10.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = "py", "-3.10"
try {
    & $python --version | Out-Null
} catch {
    Write-Error "Python 3.10 not found. Install from python.org or set up py launcher."
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    & $python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q

Write-Host ""
python calibration_9point.py @args
