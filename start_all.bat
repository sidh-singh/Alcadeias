@echo off
REM === Alcadeias — Launch ALL symbols as separate processes ===
REM Usage: start_all.bat [mode]
REM   mode: demo (default), live
REM
REM Each symbol runs in its own independent process,
REM eliminating MT5 threading issues with SHA candle overlap.

set "MODE=%~1"
if "%MODE%"=="" set "MODE=demo"

echo ============================================================
echo   LAUNCHING ALL SYMBOLS as SEPARATE PROCESSES
echo   Mode: %MODE%
echo ============================================================
echo.

REM Launch each symbol in its own terminal window
start "Alcadeias - BTCUSD" cmd /k "start_btcusd.bat %MODE%"
timeout /t 3 /nobreak > nul

start "Alcadeias - XAUUSDm" cmd /k "start_xauusd.bat %MODE%"
timeout /t 3 /nobreak > nul

start "Alcadeias - XAGUSDm" cmd /k "start_xagusd.bat %MODE%"

echo.
echo All 3 symbol processes launched in separate windows.
echo Close individual windows to stop specific symbols.
echo.
