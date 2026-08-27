@echo off
chcp 65001 > nul
echo ===================================================
echo 🛑 Orqa fondagi Telegram AI Agent to'xtatilmoqda...
echo ===================================================
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*agent.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host 'To`xtatildi PID:' $_.ProcessId }"
echo.
echo ✅ Agent to'xtatildi.
pause
