@echo off
REM === Alcadeias: the safety of this bot's account, from the server itself ===
REM Usage: safety.bat status        what the safety says now
REM        safety.bat unblock       let the bots trade again after a block
REM        safety.bat on            turn the safety ON
REM        safety.bat off           turn the safety OFF
REM        safety.bat new-account   only after this account was replaced by a new one, with both bots stopped
REM
REM No PIN is asked here: whoever can use this server can use these commands.
REM The same rules as start_job.bat: plain ASCII, no bracket blocks, one-line if only.

setlocal
cd /d "%~dp0"
if "%~1"=="" goto usage

set "PYTHON_EXE="
call find_python.bat
if not defined PYTHON_EXE goto no_python

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"%PYTHON_EXE%" -B safety.py %1
set "SAFETY_EXIT=%ERRORLEVEL%"
if not defined ALCADEIAS_NO_PAUSE pause
exit /b %SAFETY_EXIT%

:usage
echo.
echo Type one word after the file name:
echo.
echo     safety.bat status        what the safety of this account says now
echo     safety.bat unblock       let the bots trade again after a block
echo     safety.bat on            turn the safety ON
echo     safety.bat off           turn the safety OFF
echo     safety.bat new-account   only after this account was replaced by a new one, with both bots stopped
echo.
echo No PIN is asked here. Nothing was changed.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1

:no_python
echo Nothing was changed.
if not defined ALCADEIAS_NO_PAUSE pause
exit /b 1
