# IBKR Trade Alerts

Companion app that watches Interactive Brokers (TWS / Gateway) and posts trade alerts to Telegram.

## Quick start

### Mac
1. Double-click **`install_mac.command`** once (installs Python 3.12 + packages if needed).
2. Put your Telegram bot token / chat id in **`env/secrets.env`**.
3. Double-click **`start_mac.command`** to open the companion.
4. Use **`stop_mac.command`** to quit.

### Windows
1. Double-click **`install_windows.bat`** once.
2. Edit **`env\secrets.env`**.
3. Double-click **`start_windows.bat`**.
4. Use **`stop_windows.bat`** to quit.

Settings (connection, messages, shortcuts, room, appearance / font size) are inside the companion via the **⚙** button — no separate settings launcher. Each start also refreshes packages from `src/requirements.txt`.

## What you see in this folder

| Item | Purpose |
|------|---------|
| `start_mac.command` / `start_windows.bat` | Launch the app (also refreshes packages) |
| `stop_mac.command` / `stop_windows.bat` | Stop the app |
| `install_mac.command` / `install_windows.bat` | First-time Python + dependency install |
| `env/` | Your local settings (examples + your real files) |
| `src/` | Application code (you normally don’t need to open this) |

## Settings files (`env/`)

| File | Contents |
|------|----------|
| `secrets.env` | Telegram bot token + chat id (**do not commit**) |
| `.env` | IBKR host / port / client id / auto-stop |
| `messages.env` | Telegram message templates |
| `app_config.json` | Toggles, shortcuts, percentages, UI prefs |
| `*.example` | Safe templates to copy from |

On first run, missing files are created from the examples. Existing files are **never** overwritten by updates.

## IBKR tip

Use **Client ID 0** (and Master API Client ID 0 in TWS/Gateway) so manual orders are visible to the monitor.
