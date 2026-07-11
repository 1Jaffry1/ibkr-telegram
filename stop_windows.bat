@echo off
cls
color 0C
echo.
echo ========================================
echo    Stopping IBKR Trade Alerts...
echo ========================================
echo.

taskkill /F /IM python.exe

echo.
echo ✓ Alerts stopped
echo.
pause