@echo off
REM === Alcadeias: put this bot's logs, journal and state into one zip file to send ===
REM Usage: collect_logs.bat
REM
REM The zip goes into the folder exports beside the bot's output folder. Its full path is printed at the end.
REM It never holds mt5_credentials.json or the safety PIN. The bot can keep running while this runs.
REM The same rules as start_job.bat: plain ASCII, no bracket blocks, one-line if only.

setlocal
cd /d "%~dp0"

set "PYTHON_EXE="
call find_python.bat
if not defined PYTHON_EXE goto no_python

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"%PYTHON_EXE%" -B collect_logs.py %*
set "COLLECT_EXIT=%ERRORLEVEL%"
if not defined ALCADEIAS_NO_PAUSE pause
exit /b %COLLECT_EXIT%

:no_python
echo Nothing was collected.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1
