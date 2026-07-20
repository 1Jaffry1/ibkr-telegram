"""Shared app configuration: asset toggles, shortcuts, and percentage baselines."""

import json
import os
import shutil
import uuid
from pathlib import Path
from dotenv import dotenv_values, load_dotenv

# Project layout:
#   repo/
#     env/   ← user settings (gitignored locals + committed *.example)
#     src/   ← application code (this file lives here)
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_DIR = ROOT_DIR / "env"
SRC_DIR = Path(__file__).resolve().parent

CONFIG_PATH = str(ENV_DIR / "app_config.json")
ENV_PATH = str(ENV_DIR / ".env")
SECRETS_PATH = str(ENV_DIR / "secrets.env")
MESSAGES_PATH = str(ENV_DIR / "messages.env")
SUMMARY_PATH = str(ENV_DIR / "trade_summary.json")

# (local file, example template) — examples are committed; locals are gitignored.
LOCAL_SETTING_BOOTSTRAP = (
    (ENV_PATH, str(ENV_DIR / ".env.example")),
    (MESSAGES_PATH, str(ENV_DIR / "messages.env.example")),
    (SECRETS_PATH, str(ENV_DIR / "secrets.env.example")),
    (CONFIG_PATH, str(ENV_DIR / "app_config.example.json")),
)

# Older installs kept settings in the repo root — migrate once, never overwrite env/.
_LEGACY_ROOT_FILES = (
    (ROOT_DIR / ".env", ENV_PATH),
    (ROOT_DIR / "messages.env", MESSAGES_PATH),
    (ROOT_DIR / "secrets.env", SECRETS_PATH),
    (ROOT_DIR / "app_config.json", CONFIG_PATH),
    (ROOT_DIR / "trade_summary.json", SUMMARY_PATH),
)

SECRET_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
CONNECTION_KEYS = (
    "IBKR_HOST",
    "IBKR_PORT",
    "IBKR_CLIENT_ID",
    "AUTO_STOP_ENABLED",
    "STOP_TIME",
)
MESSAGE_KEYS = (
    "ORDER_MESSAGE",
    "ORDER_OPTION_MESSAGE",
    "ORDER_FUTURE_MESSAGE",
    "TRADE_MESSAGE",
    "OPTION_MESSAGE",
    "FUTURE_MESSAGE",
    "SUMMARY_MESSAGE",
    "LONG_TERM_SUMMARY_MESSAGE",
    "CONNECTED_MESSAGE",
    "CLOSED_MESSAGE",
)

DEFAULT_SHORTCUTS = [
    {"id": "starting_trade", "label": "Starting Trade", "message": "🟢 *Starting trade*"},
    {"id": "ending_trade", "label": "Ending Trade", "message": "🔴 *Ending trade*"},
    {"id": "trimming", "label": "Trimming", "message": "✂️ *Trimming*"},
]

SUMMARY_INDICATOR_ROLES = ("green", "red", "close")

DEFAULT_SUMMARY_INDICATORS = {
    "green": [],
    "red": [],
    "close": [],
}

DEFAULT_CONFIG = {
    "monitor_stocks": True,
    "monitor_options": True,
    "monitor_futures": True,
    "notify_order_submitted": True,
    "seen_setup_guide": False,
    "dark_mode": False,
    "ui_theme": "classic",
    "ui_font_size": 13,
    "window_geometry": "",
    "room": {
        "open_button": "OPEN ROOM",
        "close_button": "CLOSE ROOM",
        "open_text": "ROOM OPEN",
        "closed_text": "ROOM CLOSED",
    },
    "shortcuts": DEFAULT_SHORTCUTS,
    "summary_indicators": DEFAULT_SUMMARY_INDICATORS,
    # Shortcut ids that increment the semi-unique trade ID ({cnt})
    "trade_counter_shortcuts": [],
    "percentages": {
        "defaults": {
            "stock": {"unit": "quantity", "value": 100},
            "option": {"unit": "quantity", "value": 1},
            "future": {"unit": "quantity", "value": 1},
        },
        "exceptions": [
            # Example: {"symbol": "GLD", "asset": "option", "unit": "quantity", "value": 8}
        ],
    },
}


def migrate_legacy_settings():
    """Move root-level settings into env/ once (does not overwrite existing env files)."""
    ENV_DIR.mkdir(parents=True, exist_ok=True)
    moved = []
    for src, dest in _LEGACY_ROOT_FILES:
        try:
            if src.is_file() and not os.path.exists(dest):
                shutil.move(str(src), dest)
                moved.append(dest)
        except OSError:
            continue
    return moved


def ensure_local_settings():
    """
    Create missing local settings from committed *.example files.

    Never overwrites an existing file — safe across git pull / first run.
    """
    ENV_DIR.mkdir(parents=True, exist_ok=True)
    migrate_legacy_settings()
    created = []
    for dest, example in LOCAL_SETTING_BOOTSTRAP:
        if os.path.exists(dest):
            continue
        if os.path.exists(example):
            shutil.copyfile(example, dest)
            created.append(dest)
            continue
        if dest == CONFIG_PATH:
            # Fallback if example is missing
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
                f.write("\n")
            created.append(dest)
    return created


def load_env_files(override=True):
    """Load .env, then messages.env, then secrets.env on top."""
    ensure_local_settings()
    if os.path.exists(ENV_PATH):
        load_dotenv(ENV_PATH, override=override)
    if os.path.exists(MESSAGES_PATH):
        load_dotenv(MESSAGES_PATH, override=True)
    if os.path.exists(SECRETS_PATH):
        load_dotenv(SECRETS_PATH, override=True)


def read_env_values():
    """Return merged values from .env, messages.env, and secrets.env for the settings UI."""
    ensure_local_settings()
    values = {}
    for path in (ENV_PATH, MESSAGES_PATH, SECRETS_PATH):
        if os.path.exists(path):
            values.update(dotenv_values(path) or {})
    return values


def write_env_file(path, config):
    with open(path, "w", encoding="utf-8") as f:
        for key, value in config.items():
            value = str(value).replace('"', '\\"')
            f.write(f'{key}="{value}"\n')


def _read_env_file_dict(path):
    if not os.path.exists(path):
        return {}
    return dict(dotenv_values(path) or {})


def _merge_env_update(path, updates):
    """
    Update keys in an env file without dropping unrelated existing keys.
    Existing values for keys in `updates` are replaced; others are kept.
    """
    merged = _read_env_file_dict(path)
    for key, value in updates.items():
        if value is None:
            continue
        merged[key] = value
    write_env_file(path, merged)
    return merged


def save_env_and_secrets(all_config):
    """Split settings into .env, messages.env, and secrets.env (merge-safe)."""
    secrets = {key: all_config[key] for key in SECRET_KEYS if key in all_config}
    messages = {key: all_config[key] for key in MESSAGE_KEYS if key in all_config}
    connection = {key: all_config[key] for key in CONNECTION_KEYS if key in all_config}

    # Any unexpected keys go into .env so nothing is dropped.
    known = set(SECRET_KEYS) | set(MESSAGE_KEYS) | set(CONNECTION_KEYS)
    for key, value in all_config.items():
        if key not in known:
            connection[key] = value

    _merge_env_update(ENV_PATH, connection)
    _merge_env_update(MESSAGES_PATH, messages)
    _merge_env_update(SECRETS_PATH, secrets)
    load_env_files(override=True)


def _deep_merge_defaults(data):
    """Ensure required keys exist without wiping user values."""
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    if not isinstance(data, dict):
        return merged

    for key in ("monitor_stocks", "monitor_options", "monitor_futures", "notify_order_submitted", "seen_setup_guide", "dark_mode"):
        if key in data:
            merged[key] = bool(data[key])

    try:
        font_size = int(data.get("ui_font_size", merged.get("ui_font_size", 13)))
    except (TypeError, ValueError):
        font_size = 13
    merged["ui_font_size"] = max(10, min(22, font_size))

    geometry = str(data.get("window_geometry") or "").strip()
    if geometry:
        merged["window_geometry"] = geometry

    if isinstance(data.get("shortcuts"), list) and data["shortcuts"]:
        shortcuts = []
        for item in data["shortcuts"]:
            if not isinstance(item, dict):
                continue
            shortcuts.append({
                "id": item.get("id") or str(uuid.uuid4()),
                "label": str(item.get("label", "Shortcut")).strip() or "Shortcut",
                "message": str(item.get("message", "")),
            })
        if shortcuts:
            merged["shortcuts"] = shortcuts

    shortcut_ids = {item["id"] for item in merged["shortcuts"]}
    indicators = data.get("summary_indicators") or {}
    if isinstance(indicators, dict):
        cleaned_indicators = {role: [] for role in SUMMARY_INDICATOR_ROLES}
        claimed = set()
        for role in SUMMARY_INDICATOR_ROLES:
            values = indicators.get(role) or []
            if not isinstance(values, list):
                continue
            for raw_id in values:
                sid = str(raw_id or "").strip()
                if not sid or sid not in shortcut_ids or sid in claimed:
                    continue
                cleaned_indicators[role].append(sid)
                claimed.add(sid)
        merged["summary_indicators"] = cleaned_indicators

    counter_shortcuts = []
    raw_counter = data.get("trade_counter_shortcuts") or []
    if isinstance(raw_counter, list):
        seen = set()
        for raw_id in raw_counter:
            sid = str(raw_id or "").strip()
            if not sid or sid not in shortcut_ids or sid in seen:
                continue
            counter_shortcuts.append(sid)
            seen.add(sid)
    merged["trade_counter_shortcuts"] = counter_shortcuts

    room = data.get("room") or {}
    if isinstance(room, dict):
        for key in ("open_button", "close_button", "open_text", "closed_text"):
            value = str(room.get(key, merged["room"][key])).strip()
            if value:
                merged["room"][key] = value

    pct = data.get("percentages") or {}
    if isinstance(pct, dict):
        defaults = pct.get("defaults") or {}
        for asset in ("stock", "option", "future"):
            src = defaults.get(asset) or {}
            unit = str(src.get("unit", merged["percentages"]["defaults"][asset]["unit"])).lower()
            if unit not in ("quantity", "dollars"):
                unit = "quantity"
            try:
                value = float(src.get("value", merged["percentages"]["defaults"][asset]["value"]))
            except (TypeError, ValueError):
                value = merged["percentages"]["defaults"][asset]["value"]
            merged["percentages"]["defaults"][asset] = {"unit": unit, "value": value}

        exceptions = []
        for item in pct.get("exceptions") or []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            unit = str(item.get("unit", "quantity")).lower()
            if unit not in ("quantity", "dollars"):
                unit = "quantity"
            asset = str(item.get("asset", "any")).lower()
            if asset not in ("stock", "option", "future", "any"):
                asset = "any"
            try:
                value = float(item.get("value", 0))
            except (TypeError, ValueError):
                continue
            if value <= 0:
                continue
            exceptions.append({
                "symbol": symbol,
                "asset": asset,
                "unit": unit,
                "value": value,
            })
        merged["percentages"]["exceptions"] = exceptions

    # Keep any unknown top-level keys the user (or older versions) stored.
    if isinstance(data, dict):
        known = set(DEFAULT_CONFIG.keys())
        for key, value in data.items():
            if key not in known:
                merged[key] = value

    return merged


def load_config():
    ensure_local_settings()
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}

    return _deep_merge_defaults(data)


def save_config(config):
    """
    Save app_config.json.

    Merges with any existing on-disk config first so a partial in-memory
    update cannot wipe unrelated user fields.
    """
    ensure_local_settings()
    existing = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            existing = {}

    if not isinstance(existing, dict):
        existing = {}
    if not isinstance(config, dict):
        config = {}

    combined = dict(existing)
    combined.update(config)
    cleaned = _deep_merge_defaults(combined)
    # Re-apply unknown keys from both existing and incoming config
    known = set(DEFAULT_CONFIG.keys())
    for source in (existing, config):
        if isinstance(source, dict):
            for key, value in source.items():
                if key not in known:
                    cleaned[key] = value

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2)
        f.write("\n")
    return cleaned


def asset_class_for_contract(contract):
    sec = getattr(contract, "secType", "") or ""
    if sec in {"OPT", "FOP", "IOPT"}:
        return "option"
    if sec in {"FUT", "CONTFUT"}:
        return "future"
    return "stock"


def is_asset_enabled(config, contract):
    asset = asset_class_for_contract(contract)
    if asset == "option":
        return bool(config.get("monitor_options", True))
    if asset == "future":
        return bool(config.get("monitor_futures", True))
    return bool(config.get("monitor_stocks", True))


def resolve_baseline(config, symbol, asset):
    """Return (unit, value) for a symbol/asset using exceptions then defaults."""
    symbol = (symbol or "").strip().upper()
    pct = config.get("percentages") or {}
    exceptions = pct.get("exceptions") or []

    specific = None
    any_match = None
    for item in exceptions:
        if item.get("symbol", "").upper() != symbol:
            continue
        item_asset = item.get("asset", "any")
        if item_asset == asset:
            specific = item
            break
        if item_asset == "any" and any_match is None:
            any_match = item

    chosen = specific or any_match
    if chosen:
        return chosen["unit"], float(chosen["value"])

    defaults = (pct.get("defaults") or {}).get(asset) or {"unit": "quantity", "value": 1}
    return defaults.get("unit", "quantity"), float(defaults.get("value", 1))


def calculate_percentage(config, contract, quantity, price=0):
    """Return traded size as % of the configured 100% baseline."""
    asset = asset_class_for_contract(contract)
    symbol = getattr(contract, "symbol", "") or ""
    unit, baseline = resolve_baseline(config, symbol, asset)
    if baseline <= 0:
        return None

    qty = float(quantity or 0)
    px = float(price or 0)

    if unit == "dollars":
        multiplier = 1.0
        raw_mult = getattr(contract, "multiplier", "") or ""
        try:
            if raw_mult:
                multiplier = float(raw_mult)
        except (TypeError, ValueError):
            multiplier = 1.0
        if asset == "option" and multiplier == 1.0:
            multiplier = 100.0
        traded_value = qty * px * multiplier
        pct = (traded_value / baseline) * 100.0
    else:
        pct = (qty / baseline) * 100.0

    if pct == int(pct):
        return str(int(pct))
    return f"{pct:.2f}".rstrip("0").rstrip(".")


def summary_indicators(config=None):
    """Return {green: [ids], red: [ids], close: [ids]} from config."""
    cfg = config if isinstance(config, dict) else load_config()
    indicators = cfg.get("summary_indicators") or {}
    result = {role: [] for role in SUMMARY_INDICATOR_ROLES}
    if not isinstance(indicators, dict):
        return result
    for role in SUMMARY_INDICATOR_ROLES:
        values = indicators.get(role) or []
        if isinstance(values, list):
            result[role] = [str(v) for v in values if str(v or "").strip()]
    return result


def summary_role_for_shortcut(shortcut_id, config=None):
    """Return 'green', 'red', 'close', or None for a shortcut id."""
    sid = str(shortcut_id or "").strip()
    if not sid:
        return None
    indicators = summary_indicators(config)
    for role in SUMMARY_INDICATOR_ROLES:
        if sid in indicators[role]:
            return role
    return None


def shortcut_increments_counter(shortcut_id, config=None):
    """True if this shortcut should bump the trade ID counter."""
    sid = str(shortcut_id or "").strip()
    if not sid:
        return False
    cfg = config if isinstance(config, dict) else load_config()
    ids = cfg.get("trade_counter_shortcuts") or []
    return sid in [str(v) for v in ids]


def format_percentage_label(pct):
    if pct is None:
        return "n/a"
    return f"{pct}%"
