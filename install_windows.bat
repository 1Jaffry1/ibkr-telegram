@echo off
cls
color 0A
echo.
echo ========================================
echo    IBKR Trade Alerts — Install
echo ========================================
echo.
echo This will create .venv and install packages from src\requirements.txt
echo Make sure Python 3.10+ (with Tcl/Tk) is on PATH.
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo Error: python not found on PATH.
    echo Install from https://www.python.org/downloads/ and check "Add to PATH" + Tcl/Tk.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create .venv
        pause
        exit /b 1
    )
)

echo Upgrading pip and installing requirements...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r "src\requirements.txt"
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

if not exist "env" mkdir env
if not exist "env\.env" if exist "env\.env.example" copy /Y "env\.env.example" "env\.env" >nul
if not exist "env\messages.env" if exist "env\messages.env.example" copy /Y "env\messages.env.example" "env\messages.env" >nul
if not exist "env\secrets.env" if exist "env\secrets.env.example" copy /Y "env\secrets.env.example" "env\secrets.env" >nul
if not exist "env\app_config.json" if exist "env\app_config.example.json" copy /Y "env\app_config.example.json" "env\app_config.json" >nul

echo.
echo Install complete. Run start_windows.bat to open the companion.
echo Edit env\secrets.env for your Telegram bot token / chat id.
echo.
pause
