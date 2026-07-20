#!/bin/bash
# One-time (or anytime) installer: Python 3.12 + Tk + venv + requirements.
cd "$(dirname "$0")"
source "./ensure_venv.sh"

clear
printf "\e[32m"
echo ""
echo "========================================"
echo "    IBKR Trade Alerts — Install"
echo "========================================"
echo ""

if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Install from https://brew.sh then re-run this script."
    printf "\e[0m"
    read -p "Press [Enter] to continue..."
    close_terminal 1
fi

echo "Installing Python 3.12 + Tkinter (Homebrew)..."
brew install python@3.12 python-tk@3.12 || {
    echo "Homebrew install failed."
    printf "\e[0m"
    read -p "Press [Enter] to continue..."
    close_terminal 1
}

# Recreate venv if broken / missing
if [ ! -x "$VENV_PYTHON" ]; then
    rm -rf "$VENV_DIR"
fi

if ! ensure_venv; then
    printf "\e[0m"
    read -p "Press [Enter] to continue..."
    close_terminal 1
fi

echo "Installing / updating Python packages..."
install_requirements || true

ensure_local_settings

echo ""
echo "✅ Install complete."
echo "   Double-click start_mac.command to open the companion."
echo "   Edit secrets in env/secrets.env (Telegram token / chat id)."
echo ""
printf "\e[0m"
read -p "Press [Enter] to continue..."
close_terminal 0
