#!/bin/bash
cd "$(dirname "$0")"

source "./ensure_venv.sh"

clear
printf "\e[32m"
# Stop companion window / any leftover monitor process
pkill -f "src/gui.py" 2>/dev/null
pkill -f "gui.py" 2>/dev/null
pkill -f "client.py" 2>/dev/null
echo "✅ Alerts stopped (companion window closed if it was open)"
printf "\e[0m"
sleep 1
close_terminal 0
