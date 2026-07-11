@echo off
cls
color 0A
echo.
echo ========================================
echo    IBKR Trade Alerts - Starting...
echo ========================================
echo.
echo Your alerts will be sent to Telegram
echo Press Ctrl+C to stop the script
echo.
pause

python client.py

echo.
echo ========================================
echo    Script stopped
echo ========================================
echo.
pause