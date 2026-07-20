@echo off
cls
color 0A
echo.
echo ========================================
echo    IBKR Trade Alerts
echo ========================================
echo.
echo Opening companion window...
echo.

if not exist ".venv\Scripts\python.exe" (
    echo No virtualenv yet. Running install_windows.bat...
    call "%~dp0install_windows.bat"
)

if not exist "env" mkdir env
if not exist "env\.env" if exist "env\.env.example" copy /Y "env\.env.example" "env\.env" >nul
if not exist "env\messages.env" if exist "env\messages.env.example" copy /Y "env\messages.env.example" "env\messages.env" >nul
if not exist "env\secrets.env" if exist "env\secrets.env.example" copy /Y "env\secrets.env.example" "env\secrets.env" >nul
if not exist "env\app_config.json" if exist "env\app_config.example.json" copy /Y "env\app_config.example.json" "env\app_config.json" >nul

echo Checking packages...
".venv\Scripts\python.exe" -m pip install -q -r "src\requirements.txt"

set PYTHONPATH=%~dp0src;%PYTHONPATH%
".venv\Scripts\python.exe" "%~dp0src\gui.py"

if errorlevel 1 (
    echo.
    echo Error: Failed to start. Try install_windows.bat first.
    echo.
    pause
)
