@echo off
REM === Alcadeias — BTCUSD Single-Symbol Process ===
REM Usage: start_btcusd.bat [mode]
REM   mode: demo (default), live

REM === Define Python installation path explicitly ===
set "PYTHON_ROOT=C:\Users\Administrator\AppData\Local\Programs\Python\Python311"
set "PYTHON_EXE=%PYTHON_ROOT%\python.exe"

REM --- Ensure UTF-8 ---
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM === Get mode from parameter (default to demo) ===
set "MODE=%~1"
if "%MODE%"=="" set "MODE=demo"

echo ============================================================
echo   STARTING BTCUSD on %MODE% ACCOUNT
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

"%PYTHON_EXE%" -X utf8 -u app.py %MODE% --symbol BTCUSD

echo.
echo ============= BTCUSD PROCESS STOPPED =============
