$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..\backend')
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.13 -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
