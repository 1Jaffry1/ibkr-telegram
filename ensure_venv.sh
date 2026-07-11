#!/bin/bash
# Bootstrap the local Python virtual environment for macOS launchers.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

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
        echo ""
        return 1
    fi

    if ! "$PYTHON312" -c "import tkinter" 2>/dev/null; then
        echo "Error: Tkinter is not available for Python 3.12."
        echo ""
        echo "Install it with Homebrew:"
        echo "  brew install python-tk@3.12"
        echo ""
        return 1
    fi

    if ! "$PYTHON312" -m venv "$VENV_DIR"; then
        echo "Error: Failed to create virtual environment."
        return 1
    fi

    if ! "$VENV_PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"; then
        echo "Error: Failed to install Python dependencies."
        return 1
    fi

    echo "Setup complete."
    echo ""
    return 0
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
