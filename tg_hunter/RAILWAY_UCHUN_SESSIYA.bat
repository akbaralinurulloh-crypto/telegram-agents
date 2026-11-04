@echo off
setlocal
cd /d "%~dp0"
echo.
echo ==== TG Hunter: Railway uchun Telegram sessiyasi ====
echo Bu fayl: 1) noutbukdagi agentni to'xtatadi, 2) Telegramga QAYTA kiritadi, 3) Railway uchun hamma o'zgaruvchilarni clipboardga nusxalaydi.
echo.
echo [1/4] Noutbukdagi agent to'xtatilmoqda...
docker compose down
echo.
echo [2/4] Dastur yangilanmoqda (1-3 daqiqa)...
docker compose build
if errorlevel 1 goto xato
if exist data\hunter.session del /q data\hunter.session
if exist data\hunter.session-journal del /q data\hunter.session-journal
echo.
echo [3/4] Telegramga kirish: telefon raqamingiz (+998...) va Telegramga kelgan KOD so'raladi.
echo       Kodni hech kimga va hech qaysi chatga yubormang!
docker compose run --rm hunter python -m scripts.login
if errorlevel 1 goto xato
echo.
echo [4/4] Railway uchun o'zgaruvchilar clipboardga nusxalanmoqda...
docker compose run --rm hunter python -m scripts.export_session --railway --out data/railway_variables.txt
if errorlevel 1 goto xato
type data\railway_variables.txt | clip
if errorlevel 1 goto xato
del /q data\railway_variables.txt
del /q data\hunter.session
if exist data\hunter.session-journal del /q data\hunter.session-journal
echo.
echo TAYYOR. Hamma o'zgaruvchilar clipboardda: Railway "Variables" - "Raw Editor" ga bitta Ctrl+V qiling.
echo Ichida Telegram akkauntingizga TO'LIQ kirish bor: boshqa joyga yozmang, hech kimga bermang.
echo Noutbukdagi sessiya nusxasi o'chirildi, shunda agent ikki joyda bir vaqtda ishlab qolmaydi.
echo.
pause
exit /b 0

:xato
echo.
echo XATO chiqdi. Oynadagi yozuvni skrinshot qilib yuboring.
pause
exit /b 1
