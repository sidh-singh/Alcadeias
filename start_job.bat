@echo off
REM === Alcadeias: start this branch's bot on its REAL-MONEY account ===
REM Usage: start_job.bat live
REM
REM The word live is required. This branch has no demo mode and no default mode.
REM The bot is started again 30 seconds after it ends, whatever the reason: a crash, a lost terminal.
REM It is NOT started again when it says that only you can fix the problem, or when you stop it yourself.
REM Close this window to stop the bot. That does not close its open trades.
REM
REM Nobody can run a .bat file where this one is written, so it follows strict rules, checked by
REM tests_demo/test_launchers.py: plain ASCII, no bracket blocks, one-line if only, the exit code compared as text.

setlocal
cd /d "%~dp0"

REM === This branch: its name, its symbol and its output folder, from branch_env.bat ===
REM     Cleared first, so that a window used for another branch before cannot lend its values.
set "BRANCH="
set "SYMBOL="
set "OUT_DIR="
if not exist "branch_env.bat" goto no_env
call branch_env.bat
if not defined BRANCH goto no_env
if not defined SYMBOL goto no_env
if not defined OUT_DIR goto no_env

REM === The mode: only the word live starts the bot ===
if /i not "%~1"=="live" goto wrong_mode
title %BRANCH% bot - %SYMBOL% - REAL MONEY

REM === Python ===
set "PYTHON_EXE="
call find_python.bat
if not defined PYTHON_EXE goto no_python
echo Python: "%PYTHON_EXE%"
echo.

REM --- Ensure UTF-8 in Windows console and Python for Jenkins compatibility ---
REM Set console code page to UTF-8 and force Python to use UTF-8 IO
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM === The packages the bot needs ===
REM     Looked for at every start. Installed only when one is missing, in the versions of requirements.txt.
"%PYTHON_EXE%" -c "import MetaTrader5, pandas, numpy" 1>nul 2>nul
if not errorlevel 1 goto deps_ok
echo The Python packages of the bot are missing. Installing the versions of requirements.txt ...
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 goto deps_failed
"%PYTHON_EXE%" -c "import MetaTrader5, pandas, numpy"
if errorlevel 1 goto deps_failed
:deps_ok

echo ============================================================
echo   STARTING %BRANCH% - %SYMBOL% on the LIVE ACCOUNT
echo ============================================================
echo.
echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo   WARNING: LIVE MODE - TRADING WITH REAL MONEY!
echo   Close this window within 5 seconds if you do not want that.
echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo.
ping -n 6 127.0.0.1 > nul

REM === Run the bot. It is started again 30 s after it ends, except on the three exit codes below ===
REM     78 and 2: something only the owner can fix. 0: the owner stopped it.
:run_bot
"%PYTHON_EXE%" -X utf8 -u app.py live --symbol %SYMBOL%
set "BOT_EXIT=%ERRORLEVEL%"
if "%BOT_EXIT%"=="78" goto needs_owner
if "%BOT_EXIT%"=="2" goto needs_owner
if "%BOT_EXIT%"=="0" goto stopped
echo app.py ended with code %BOT_EXIT% - it starts again in 30 seconds. Close this window to stop the bot.
ping -n 31 127.0.0.1 > nul
goto run_bot

:needs_owner
echo.
echo %BRANCH% has stopped and will NOT start again by itself. Read the lines above, fix what they say, then start this file again.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b %BOT_EXIT%

:stopped
echo.
echo %BRANCH% was stopped by you and does not start again by itself.
echo Its open trades are NOT closed. Nothing manages them until the bot runs again.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 0

:wrong_mode
echo.
echo This is the real-money branch %BRANCH%. It has no demo mode.
echo Start it with the word live after the file name:
echo.
echo     start_job.bat live
echo.
echo Nothing was started.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1

:no_env
echo.
echo The file branch_env.bat is missing or not complete in this folder:
echo   "%CD%"
echo It must set BRANCH, SYMBOL and OUT_DIR. To get the file back, run this in this folder:
echo.
echo     git checkout -- branch_env.bat
echo.
echo Nothing was started.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1

:no_python
echo Nothing was started.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1

:deps_failed
echo.
echo The Python packages of the bot could not be installed or loaded. The lines above say why.
echo Check that this server reaches the internet, then start this file again.
echo To try the install by hand, run this in this folder:
echo.
echo     "%PYTHON_EXE%" -m pip install -r requirements.txt
echo.
echo Nothing was started.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1
