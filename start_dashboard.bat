@echo off
REM === Alcadeias: start this branch's dashboard ===
REM Usage: start_dashboard.bat
REM
REM A word after the file name, for example live, is accepted and ignored: the dashboard has no mode.
REM Run from the bot's own folder, wherever it was started from: Task Scheduler without a start folder, a shortcut.
REM The same rules as start_job.bat: plain ASCII, no bracket blocks, one-line if only.

setlocal
cd /d "%~dp0"

REM === This branch: its name and its output folder, from branch_env.bat ===
set "BRANCH="
set "SYMBOL="
set "OUT_DIR="
if not exist "branch_env.bat" goto no_env
call branch_env.bat
if not defined BRANCH goto no_env
if not defined SYMBOL goto no_env
if not defined OUT_DIR goto no_env
title %BRANCH% dashboard - %SYMBOL%

REM === The dashboard's own Python environment ===
REM     Dash and plotly go into a private environment in this bot's output folder, so the shared Python that the
REM     bots use is never changed. Made once, which takes a minute or two, then reused.
REM     Versions: the ones requirements.txt pins. An unpinned install could bring Dash 3 or plotly 6.
set "DASH_ENV=%OUT_DIR%\dash_env"
set "DASH_PY=%DASH_ENV%\Scripts\python.exe"
if exist "%DASH_PY%" goto env_ready
set "PYTHON_EXE="
call find_python.bat
if not defined PYTHON_EXE goto no_python
echo Python: "%PYTHON_EXE%"
echo Creating the dashboard's own Python environment in "%DASH_ENV%" ...
"%PYTHON_EXE%" -m venv "%DASH_ENV%"
if errorlevel 1 goto venv_failed
:env_ready
if exist "%DASH_ENV%\dash_2.18.2_plotly_5.24.1.flag" goto deps_ready
echo Installing dash 2.18.2 and plotly 5.24.1 into "%DASH_ENV%" ...
"%DASH_PY%" -m pip install dash==2.18.2 plotly==5.24.1
if errorlevel 1 goto pip_failed
echo Dashboard dependencies installed > "%DASH_ENV%\dash_2.18.2_plotly_5.24.1.flag"
:deps_ready

echo ============================================================
echo   STARTING ALCADEIAS DASHBOARD - %BRANCH%
echo   It prints its address on the next lines.
echo ============================================================
echo.

"%DASH_PY%" -u dashboard.py
set "DASH_EXIT=%ERRORLEVEL%"

echo.
echo ============= DASHBOARD STOPPED =============
echo The bot does not need the dashboard: it trades on without it. Start this file again to get the page back.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b %DASH_EXIT%

:no_env
echo.
echo The file branch_env.bat is missing or not complete in this folder:
echo   "%CD%"
echo It must set BRANCH, SYMBOL and OUT_DIR. To get the file back, run this in this folder:
echo.
echo     git checkout -- branch_env.bat
echo.
echo The dashboard was not started.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1

:no_python
echo The dashboard was not started.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1

:venv_failed
echo.
echo Could not create the dashboard's own Python environment in "%DASH_ENV%".
echo Check that the folder "%OUT_DIR%" can be written, then run this file again.
echo The dashboard was not started.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1

:pip_failed
echo.
echo pip failed: the dashboard needs dash 2.18.2 and plotly 5.24.1. The lines above say why.
echo Check that this server reaches the internet, then run this file again.
echo If it fails again, delete the folder "%DASH_ENV%" and run this file once more.
echo The dashboard was not started.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1
