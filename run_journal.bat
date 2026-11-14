@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo .venv nahi mila - pehle run.bat ek dafa chala lein.
    pause
    exit /b 1
)

echo Trade journal bot chalu (Telegram par /add, /list, /stats).
echo Band karne ke liye Ctrl+C dabayein.
echo.
".venv\Scripts\python.exe" scripts\trade_bot.py

echo.
echo Journal bot band ho gaya.
pause >nul
