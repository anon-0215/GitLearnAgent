@echo off
setlocal

cd /d "%~dp0"
set "CONDA_ENV=D:\Programme\Anaconda\envs\gitlearnagent"
set "NPM_CMD="

if exist "%CONDA_ENV%\npm.cmd" (
  set "PATH=%CONDA_ENV%;%PATH%"
  set "NPM_CMD=%CONDA_ENV%\npm.cmd"
) else (
  for /f "delims=" %%N in ('where npm 2^>nul') do (
    if not defined NPM_CMD set "NPM_CMD=%%N"
  )
)

if not defined NPM_CMD (
  echo Cannot find npm.
  echo.
  echo Install Node.js, then run this script again.
  pause
  exit /b 1
)

if not exist "node_modules" (
  "%NPM_CMD%" install
)

"%NPM_CMD%" run dev
