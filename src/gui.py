"""
IBKR Trade Alerts — companion window entry point.

Loads the UI theme from env/app_config.json (ui_theme: classic | modern).
"""

from config_store import load_config
from themes import DEFAULT_THEME, THEMES


def main():
    theme = load_config().get("ui_theme", DEFAULT_THEME)
    module_path = THEMES.get(theme, THEMES[DEFAULT_THEME])
    module = __import__(module_path, fromlist=["main"])
    module.main()


if __name__ == "__main__":
    main()
