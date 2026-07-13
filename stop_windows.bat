@echo off
cls
color 0C
echo.
echo ========================================
echo    Stopping IBKR Trade Alerts...
echo ========================================
echo.

taskkill /F /IM python.exe /FI "WINDOWTITLE eq IBKR Trade Alerts*" >nul 2>&1
taskkill /F /FI "IMAGENAME eq python.exe" /FI "COMMANDLINE eq *gui.py*" >nul 2>&1
taskkill /F /FI "IMAGENAME eq python.exe" /FI "COMMANDLINE eq *client.py*" >nul 2>&1

echo.
echo Prefer using the Stop button in the companion window.
echo If that window is still open, close it manually.
echo.
pause
