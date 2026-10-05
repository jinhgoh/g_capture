@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto failed

if exist ".venv\Scripts\python.exe" goto check_environment
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv .venv
    if errorlevel 1 goto failed
    goto check_environment
)
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 (
    echo Python 3.10 or newer is required. Install Python with Tcl/Tk support,
    echo then run launch.bat again.
    goto failed
)
python -m venv .venv
if errorlevel 1 goto failed

:check_environment
".venv\Scripts\python.exe" -c "import sys, tkinter; sys.exit(sys.version_info < (3, 10))"
if errorlevel 1 (
    echo The local environment requires Python 3.10 or newer with Tcl/Tk support.
    goto failed
)
".venv\Scripts\python.exe" -c "import PIL, numpy, pystray" >nul 2>&1
if not errorlevel 1 goto launch
echo Installing G Capture dependencies. First-time setup requires internet access.
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

:launch
".venv\Scripts\python.exe" -c "import app"
if errorlevel 1 goto failed
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py" %*
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo G Capture could not start. Review the error above and try again.
pause
exit /b 1
