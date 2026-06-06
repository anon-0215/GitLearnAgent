@echo off
setlocal

cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHON_EXE="

if exist "D:\Programme\Anaconda\envs\gitlearnagent\python.exe" (
  set "PYTHON_EXE=D:\Programme\Anaconda\envs\gitlearnagent\python.exe"
) else (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
  )
)

if not defined PYTHON_EXE (
  echo Cannot find Python.
  echo.
  echo Install Python 3.12 or create a conda environment, then run:
  echo pip install -r requirements.txt
  pause
  exit /b 1
)

"%PYTHON_EXE%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
