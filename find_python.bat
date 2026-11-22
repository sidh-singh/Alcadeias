@echo off
REM === Alcadeias: find the Python 3.11 of this server ===
REM Called by the other launchers. It sets PYTHON_EXE to the first of these that exists:
REM   1. the full path in the variable ALCADEIAS_PYTHON, when you have set one - without quotes
REM   2. the Administrator's Python 3.11, which the old live bots use
REM   3. the Python 3.11 of the user admin
REM   4. the Python 3.11 of the Windows user who started the launcher
REM When none exists it leaves PYTHON_EXE empty and says where it looked. The caller then stops.
REM No setlocal here: the caller needs PYTHON_EXE after this file ends.

set "PYTHON_EXE="
if defined ALCADEIAS_PYTHON if exist "%ALCADEIAS_PYTHON%" set "PYTHON_EXE=%ALCADEIAS_PYTHON%"
if not defined PYTHON_EXE if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
if not defined PYTHON_EXE if exist "C:\Users\admin\AppData\Local\Programs\Python\Python311\python.exe" set "PYTHON_EXE=C:\Users\admin\AppData\Local\Programs\Python\Python311\python.exe"
if not defined PYTHON_EXE if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if defined PYTHON_EXE goto found

echo.
echo Python 3.11 was not found on this server. This file looks for python.exe in these places, in this order:
echo   1. the full path in the variable ALCADEIAS_PYTHON, when you have set one
echo   2. C:\Users\Administrator\AppData\Local\Programs\Python\Python311
echo   3. C:\Users\admin\AppData\Local\Programs\Python\Python311
echo   4. AppData\Local\Programs\Python\Python311 of the Windows user who started this file
echo Install Python 3.11 in one of them, or set ALCADEIAS_PYTHON to the full path of python.exe, without quotes.

:found
exit /b 0
