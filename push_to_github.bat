@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "GIT="
where git >nul 2>&1 && set "GIT=git"
if not defined GIT if exist "%USERPROFILE%\.qoder\bin\git\cmd\git.exe" set "GIT=%USERPROFILE%\.qoder\bin\git\cmd\git.exe"
if not defined GIT if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT if exist "%LocalAppData%\Programs\Git\cmd\git.exe" set "GIT=%LocalAppData%\Programs\Git\cmd\git.exe"

if not defined GIT (
    echo [X] Git nahi mila.
    pause
    exit /b 1
)

echo ==========================================
echo  Crypto Signal Agent - GitHub push
echo ==========================================
echo.
echo IMPORTANT: Password ki jagah TOKEN paste karein.
echo Token GitHub par banayein: Settings ^> Developer settings
echo   ^> Personal access tokens ^> Tokens ^(classic^) ^> Generate new token
echo   Scope mein "repo" tick karein, phir token copy karein (ghp_...).
echo.
echo Username pehle se bhara hua hai - sirf Password par token paste karein.
echo (Paste karne ke liye window par right-click karein.)
echo.

echo Cloud ke naye commits le raha hoon (journal auto-update hota rehta hai)...
"%GIT%" pull --rebase --autostash origin main
echo.

"%GIT%" push -u origin main
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo [OK] Push mukammal - GitHub par code chala gaya.
) else (
    echo [X] Push fail hua. Upar ki lines screenshot le kar bhejein.
)

echo.
echo Window band karne ke liye koi bhi key dabayein.
pause >nul
