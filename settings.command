#!/bin/bash
cd "$(dirname "$0")"

clear
printf "\e[32m"

echo ""
echo "========================================"
echo "    IBKR Trade Alerts - Settings"
echo "========================================"
echo ""
echo "Opening configuration window..."
echo ""

source "./ensure_venv.sh"
if ! ensure_venv; then
    printf "\e[0m"
    read -p "Press [Enter] to continue..."
    close_terminal 1
fi

"$VENV_PYTHON" gui.py

if [ $? -ne 0 ]; then
    echo ""
    echo "Error: Failed to open the settings window."
    echo "Run setup with: brew install python@3.12 python-tk@3.12"
    echo ""
    printf "\e[0m"
    read -p "Press [Enter] to continue..."
    close_terminal 1
fi

printf "\e[0m"
close_terminal 0
