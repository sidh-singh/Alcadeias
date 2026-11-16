@echo off
REM === Alcadeias Dashboard Launcher ===
REM Run from the bot's own folder, wherever it was started from (Task Scheduler without "Start in", a shortcut)
cd /d "%~dp0"
REM Usage: start_dashboard.bat [mode]
REM   mode: demo (default), live

REM === Get mode from parameter (default to demo) ===
set "MODE=%~1"
if "%MODE%"=="" set "MODE=demo"

REM === DEMO branch: live mode is disabled ===
if /i "%MODE%"=="live" (
    echo This is a DEMO branch ^(demo_hedging_btcusd7^): live mode is disabled.
    exit /b 1
)

REM === Define Python installation path based on mode ===
if /i "%MODE%"=="live" (
    set "PYTHON_ROOT=C:\Users\Administrator\AppData\Local\Programs\Python\Python311"
) else (
    set "PYTHON_ROOT=C:\Users\Administrator\AppData\Local\Programs\Python\Python311"
)
set "PYTHON_EXE=%PYTHON_ROOT%\python.exe"

echo Python path: %PYTHON_EXE%
echo.

REM === The dashboard's own Python environment ===
REM     Dash and plotly go into a private environment in this bot's output folder, so the shared Python that the
REM     live bots and their dashboards use is never changed. Made once (a minute or two), then reused.
REM     Versions: the ones requirements.txt pins (an unpinned install could bring Dash 3 or plotly 6).
set "DASH_ENV=C:\Alcadeias\demo_hedging_btcusd7\dash_env"
set "DASH_PY=%DASH_ENV%\Scripts\python.exe"
if not exist "%DASH_PY%" (
    echo Creating the dashboard's own Python environment in %DASH_ENV% ...
    "%PYTHON_EXE%" -m venv "%DASH_ENV%"
    if errorlevel 1 (
        echo Could not create %DASH_ENV%. Check that %PYTHON_EXE% exists and that C:\Alcadeias can be written, then run this again.
        pause
        exit /b 1
    )
)
if not exist "%DASH_ENV%\dash_2.18.2_plotly_5.24.1.flag" (
    echo Installing dash 2.18.2 and plotly 5.24.1 into %DASH_ENV% ...
    "%DASH_PY%" -m pip install dash==2.18.2 plotly==5.24.1
    if errorlevel 1 (
        echo pip failed: the dashboard needs dash 2.18.2 and plotly 5.24.1. Check the internet connection and run this again.
        pause
        exit /b 1
    )
    echo Dashboard dependencies installed > "%DASH_ENV%\dash_2.18.2_plotly_5.24.1.flag"
) else (
    echo Dashboard dependencies already installed in %DASH_ENV%, skipping...
)

echo ============================================================
echo   STARTING ALCADEIAS DASHBOARD
echo   It prints its address on the next lines.
echo ============================================================
echo.

"%DASH_PY%" -u dashboard.py

echo.
echo ============= DASHBOARD STOPPED =============
