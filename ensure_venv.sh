#!/bin/bash
# Bootstrap the local Python virtual environment for macOS launchers.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
REQ_FILE="$SCRIPT_DIR/src/requirements.txt"

find_python312() {
    for candidate in \
        /opt/homebrew/bin/python3.12 \
        /usr/local/bin/python3.12 \
        "$(command -v python3.12 2>/dev/null)"
    do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

ensure_venv() {
    if [ -x "$VENV_PYTHON" ]; then
        return 0
    fi

    echo ""
    echo "First-time setup: creating Python environment..."
    echo ""

    PYTHON312="$(find_python312)"
    if [ -z "$PYTHON312" ]; then
        echo "Error: Python 3.12 is required but was not found."
        echo ""
        echo "Install it with Homebrew:"
        echo "  brew install python@3.12 python-tk@3.12"
        echo "Or run: ./install_mac.command"
        echo ""
        return 1
    fi

    if ! "$PYTHON312" -c "import tkinter" 2>/dev/null; then
        echo "Error: Tkinter is not available for Python 3.12."
        echo ""
        echo "Install it with Homebrew:"
        echo "  brew install python-tk@3.12"
        echo "Or run: ./install_mac.command"
        echo ""
        return 1
    fi

    if ! "$PYTHON312" -m venv "$VENV_DIR"; then
        echo "Error: Failed to create virtual environment."
        return 1
    fi

    if ! "$VENV_PYTHON" -m pip install --upgrade pip; then
        echo "Error: Failed to upgrade pip."
        return 1
    fi

    if ! "$VENV_PYTHON" -m pip install -r "$REQ_FILE"; then
        echo "Error: Failed to install Python dependencies."
        return 1
    fi

    echo "Setup complete."
    echo ""
    return 0
}

# Quietly refresh dependencies on each launch (safe; does not touch env/ settings).
install_requirements() {
    if [ ! -x "$VENV_PYTHON" ]; then
        return 1
    fi
    "$VENV_PYTHON" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
    if ! "$VENV_PYTHON" -m pip install -q -r "$REQ_FILE"; then
        echo "Warning: could not refresh packages from src/requirements.txt"
        return 1
    fi
    return 0
}

# Copy committed env/*.example templates to env/ ONLY if missing.
ensure_local_settings() {
    mkdir -p "$SCRIPT_DIR/env"
    local pairs=(
        "env/.env:env/.env.example"
        "env/messages.env:env/messages.env.example"
        "env/secrets.env:env/secrets.env.example"
        "env/app_config.json:env/app_config.example.json"
    )
    local pair dest example
    for pair in "${pairs[@]}"; do
        dest="${pair%%:*}"
        example="${pair##*:}"
        if [ ! -f "$SCRIPT_DIR/$dest" ] && [ -f "$SCRIPT_DIR/$example" ]; then
            cp "$SCRIPT_DIR/$example" "$SCRIPT_DIR/$dest"
            echo "Created $dest from $example (edit with your values)."
        fi
    done
    # One-time migrate legacy root settings into env/
    for f in .env messages.env secrets.env app_config.json trade_summary.json; do
        if [ -f "$SCRIPT_DIR/$f" ] && [ ! -f "$SCRIPT_DIR/env/$f" ]; then
            mv "$SCRIPT_DIR/$f" "$SCRIPT_DIR/env/$f"
            echo "Moved $f → env/$f"
        fi
    done
}

close_terminal() {
    local code="${1:-0}"
    if [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ]; then
        osascript -e 'tell application "Terminal" to close front window' >/dev/null 2>&1 &
    elif [ "${TERM_PROGRAM:-}" = "iTerm.app" ]; then
        osascript -e 'tell application "iTerm" to close current window' >/dev/null 2>&1 &
    fi
    exit "$code"
}
