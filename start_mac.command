#!/bin/bash
cd "$(dirname "$0")"

clear
printf "\e[32m"

echo ""
echo "========================================"
echo "    IBKR Trade Alerts"
echo "========================================"
echo ""
echo "Opening companion window..."
echo ""

source "./ensure_venv.sh"
if ! ensure_venv; then
    printf "\e[0m"
    echo "Tip: run ./install_mac.command once to install Python + packages."
    read -p "Press [Enter] to continue..."
    close_terminal 1
fi

ensure_local_settings
echo "Checking packages..."
install_requirements || true

export PYTHONPATH="$(pwd)/src${PYTHONPATH:+:$PYTHONPATH}"
"$VENV_PYTHON" src/gui.py

if [ $? -ne 0 ]; then
    echo ""
    echo "Error: Failed to open the companion window."
    echo "Try: ./install_mac.command"
    echo ""
    printf "\e[0m"
    read -p "Press [Enter] to continue..."
    close_terminal 1
fi

printf "\e[0m"
close_terminal 0
