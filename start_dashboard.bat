@echo off
REM === Alcadeias Dashboard Launcher ===
REM Usage: start_dashboard.bat [mode]
REM   mode: demo (default), live

REM === Get mode from parameter (default to demo) ===
set "MODE=%~1"
if "%MODE%"=="" set "MODE=demo"

REM === DEMO branch: live mode is disabled ===
if /i "%MODE%"=="live" (
    echo This is a DEMO branch ^(demo_hedging_btcusd6^): live mode is disabled.
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

REM === Dash and plotly: the versions requirements.txt pins (an unpinned install could bring Dash 3 or plotly 6) ===
REM     The flag file names the versions, so a PC with an older flag installs these once.
if not exist ".\dash_2.18.2_plotly_5.24.1.flag" (
    echo Installing dashboard dependencies: dash 2.18.2, plotly 5.24.1 ...
    "%PYTHON_EXE%" -m pip install dash==2.18.2 plotly==5.24.1
    echo Dashboard dependencies installed > ".\dash_2.18.2_plotly_5.24.1.flag"
) else (
    echo Dashboard dependencies already installed, skipping...
)

echo ============================================================
echo   STARTING ALCADEIAS DASHBOARD
echo   It prints its address on the next lines.
echo ============================================================
echo.

"%PYTHON_EXE%" -u dashboard.py

echo.
echo ============= DASHBOARD STOPPED =============
