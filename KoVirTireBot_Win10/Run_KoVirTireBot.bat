@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt
py -3 -m playwright install chromium
py -3 KoVirTireBot.py
pause
