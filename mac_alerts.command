#!/bin/bash
cd "$(dirname "$0")"
clear
printf "\e[32m"
echo "🚀 Starting IBKR Trade Alerts..."

source "./ensure_venv.sh"
if ! ensure_venv; then
    printf "\e[0m"
    read -p "Press [Enter] to continue..."
    close_terminal 1
fi

printf "\e[0m"
"$VENV_PYTHON" client.py
printf "\e[32m"
echo "✅ Script stopped"
printf "\e[0m"
close_terminal 0
