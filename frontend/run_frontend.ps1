$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$CondaEnv = "D:\Programme\Anaconda\envs\gitlearnagent"
if (Test-Path $CondaEnv) {
  $env:PATH = "$CondaEnv;$env:PATH"
}

if (-not (Test-Path ".\node_modules")) {
  npm install
}

npm run dev
