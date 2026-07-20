@echo off
cls
color 0A
echo.
echo Stopping IBKR Trade Alerts...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq IBKR Trade Alerts*" >nul 2>&1
wmic process where "CommandLine like '%%src\\gui.py%%'" call terminate >nul 2>&1
wmic process where "CommandLine like '%%gui.py%%'" call terminate >nul 2>&1
echo Alerts stopped.
timeout /t 1 >nul
