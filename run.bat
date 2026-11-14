@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Virtual environment bana raha hoon...
    python -m venv .venv
)

echo [2/3] Dependencies install/update...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt

echo [3/3] Agent chala raha hoon...
".venv\Scripts\python.exe" -m agent.main

echo.
echo Done. Band karne ke liye koi bhi key dabayein.
pause >nul
