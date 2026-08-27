@echo off
title Telegram AI Agent
chcp 65001 > nul
echo ===================================================
echo 🤖 Telegram AI Agent ishga tushirilmoqda...
echo ===================================================
cd /d "%~dp0"
python agent.py
pause
