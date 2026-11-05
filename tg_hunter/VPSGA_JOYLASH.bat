@echo off
setlocal
cd /d "%~dp0"
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\vps_joylash.ps1"
echo.
pause
