@echo off
REM Simple launcher for Jarvis v2 Core (Windows).

REM Change to the directory where this script lives.
cd /d "%~dp0"

REM Create a virtual environment (if it does not exist yet).
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate the virtual environment.
call ".venv\Scripts\activate.bat"

REM Install required Python packages.
echo Installing Python dependencies...
pip install --upgrade pip
pip install -r requirements.txt

REM Run Jarvis v2 Core skeleton.
echo Running Jarvis v2 Core...
python -m app.main

REM Keep the window open so you can read any messages.
echo.
echo Jarvis v2 Core finished. Press any key to close this window.
pause >nul

