@echo off
cls
color 0A
echo.
echo ========================================
echo    IBKR Trade Alerts - Settings
echo ========================================
echo.
echo Opening configuration window...
echo.

python gui.py

if errorlevel 1 (
    echo.
    echo Error: Make sure Python is installed!
    echo.
    pause
)