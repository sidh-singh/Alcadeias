@echo off
REM === Alcadeias Dashboard Launcher ===
REM Usage: start_dashboard.bat

REM === Define Python installation path explicitly ===
set "PYTHON_ROOT=C:\Users\Administrator\AppData\Local\Programs\Python\Python311"
set "PYTHON_EXE=%PYTHON_ROOT%\python.exe"

echo Python path: %PYTHON_EXE%
echo.

REM === Check if Dash is installed ===
if not exist ".\dash_installed.flag" (
    echo Installing dashboard dependencies...
    "%PYTHON_EXE%" -m pip install dash plotly
    echo Dashboard dependencies installed > ".\dash_installed.flag"
) else (
    echo Dashboard dependencies already installed, skipping...
)

echo ============================================================
echo   STARTING ALCADEIAS DASHBOARD
echo   Open browser at http://localhost:8050
echo ============================================================
echo.

"%PYTHON_EXE%" -u dashboard.py

echo.
echo ============= DASHBOARD STOPPED =============
