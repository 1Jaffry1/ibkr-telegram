#!/bin/bash
cd "$(dirname "$0")"

source "./ensure_venv.sh"

clear
printf "\e[32m"
pkill -f "client.py"
echo "✅ Alerts stopped"
printf "\e[0m"
sleep 1
close_terminal 0
