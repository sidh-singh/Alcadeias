@echo off
REM === Generic Job Executor - Accepts mode as parameter ===
REM Usage: start_job.bat [mode]
REM 
REM Parameters:
REM   mode: demo, live (default: demo)
REM 
REM Examples:
REM   start_job.bat              # Run on DEMO account
REM   start_job.bat demo         # Run on DEMO account
REM   start_job.bat live         # Run on LIVE account

REM === Define Python installation path explicitly ===
set "PYTHON_ROOT=C:\Users\Administrator\AppData\Local\Programs\Python\Python311"
set "PYTHON_EXE=%PYTHON_ROOT%\python.exe"

echo Python path: %PYTHON_EXE%
echo.

REM --- Ensure UTF-8 in Windows console and Python for Jenkins compatibility ---
REM Set console code page to UTF-8 and force Python to use UTF-8 IO
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM === Get mode from parameter (default to demo if not provided) ===
set "MODE=%~1"
if "%MODE%"=="" set "MODE=demo"

echo ============================================================
echo   STARTING JOB on %MODE% ACCOUNT
echo ============================================================
echo.

REM === Safety warning for LIVE mode ===
if /i "%MODE%"=="live" (
    echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo   WARNING: LIVE MODE - TRADING WITH REAL MONEY!
    echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo.
    timeout /t 5 /nobreak > nul
)

REM === Check if requirements already installed (flag file used) ===
if not exist ".\deps_installed.flag" (
    echo Installing dependencies...
    "%PYTHON_EXE%" -m ensurepip --upgrade
    "%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel
    "%PYTHON_EXE%" -m pip install -r requirements.txt

    echo Dependencies installed > ".\deps_installed.flag"
) else (
    echo Dependencies already installed, skipping...
)

REM === Run job via launch_strategy.py with mode parameter ===
echo Running job on %MODE% account
"%PYTHON_EXE%" -X utf8 -u app.py %MODE%

echo.
echo ============= SCRIPT FINISHED =============
