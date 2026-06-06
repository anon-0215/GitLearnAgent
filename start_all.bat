@echo off
setlocal

cd /d "%~dp0"

start "GitLearnAgent Backend" cmd /k "D:\Project\GitLearnAgent\backend\run_backend.bat"
timeout /t 3 /nobreak >nul
start "GitLearnAgent Frontend" cmd /k "D:\Project\GitLearnAgent\frontend\run_frontend.bat"

echo GitLearnAgent is starting.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo.
echo Keep the backend and frontend windows open while using the app.
pause

