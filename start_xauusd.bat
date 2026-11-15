@echo off
REM === Alcadeias — XAUUSDm Single-Symbol Process ===
REM Usage: start_xauusd.bat [mode]
REM   mode: demo (default), live

REM === Get mode from parameter (default to demo) ===
set "MODE=%~1"
if "%MODE%"=="" set "MODE=demo"

REM === DEMO branch: live mode is disabled ===
if /i "%MODE%"=="live" (
    echo This is a DEMO branch ^(demo_hedging_xauusd7^): live mode is disabled.
    exit /b 1
)

REM === Define Python installation path based on mode ===
if /i "%MODE%"=="live" (
    set "PYTHON_ROOT=C:\Users\Administrator\AppData\Local\Programs\Python\Python311"
) else (
    set "PYTHON_ROOT=C:\Users\Administrator\AppData\Local\Programs\Python\Python311"
)
set "PYTHON_EXE=%PYTHON_ROOT%\python.exe"

REM --- Ensure UTF-8 ---
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo ============================================================
echo   STARTING XAUUSDm on %MODE% ACCOUNT
echo ============================================================
echo.

REM === Check if requirements already installed ===
if not exist ".\deps_installed.flag" (
    echo Installing dependencies...
    "%PYTHON_EXE%" -m ensurepip --upgrade
    "%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    echo Dependencies installed > ".\deps_installed.flag"
) else (
    echo Dependencies already installed, skipping...
)

REM === Run the bot; on demo it is started again 30 s after app.py exits (a crash, a lost terminal) ===
REM     Close this window (or Ctrl+C, then Y) to stop it.
:run_bot
"%PYTHON_EXE%" -X utf8 -u app.py %MODE% --symbol XAUUSDm
set "BOT_EXIT=%ERRORLEVEL%"
if /i not "%MODE%"=="demo" goto stopped
echo.
echo ============= XAUUSDm PROCESS EXITED (code %BOT_EXIT%) - restarting in 30 s =============
ping -n 31 127.0.0.1 > nul
goto run_bot

:stopped
echo.
echo ============= XAUUSDm PROCESS STOPPED =============
