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

python gui.py

if errorlevel 1 (
    echo.
    echo Error: Make sure Python is installed and dependencies are set up!
    echo Run: pip install -r requirements.txt
    echo.
    pause
)
