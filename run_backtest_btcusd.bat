@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  Alcadeias BTCUSD offline backtest launcher (no MT5 sign-in required).
REM  Mirrors start_btcusd.bat, but replays the real bot logic over history.
REM  Any extra args are passed through, e.g.:
REM      run_backtest_btcusd.bat --days 90 --balance 10000 --spread-usd 5
REM ─────────────────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=python"
if exist "venv\Scripts\python.exe" set "PYTHON_EXE=venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

"%PYTHON_EXE%" -X utf8 -u -m backtest.run_backtest %*

echo.
pause
