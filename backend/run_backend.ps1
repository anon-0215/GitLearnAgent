$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$CondaPython = "D:\Programme\Anaconda\envs\gitlearnagent\python.exe"

if (Test-Path $CondaPython) {
  $Python = $CondaPython
} else {
  if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
  }
  $Python = ".\.venv\Scripts\python.exe"
  & $Python -m pip install -r requirements.txt
}

$env:PYTHONUTF8 = "1"
& $Python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
