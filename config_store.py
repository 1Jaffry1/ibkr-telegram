"""Shared app configuration: asset toggles, shortcuts, and percentage baselines."""

import json
import os
import uuid
from dotenv import dotenv_values, load_dotenv

CONFIG_PATH = "app_config.json"
ENV_PATH = ".env"
SECRETS_PATH = "secrets.env"

SECRET_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")

DEFAULT_SHORTCUTS = [
    {"id": "starting_trade", "label": "Starting Trade", "message": "🟢 *Starting trade*"},
    {"id": "ending_trade", "label": "Ending Trade", "message": "🔴 *Ending trade*"},
    {"id": "trimming", "label": "Trimming", "message": "✂️ *Trimming*"},
]

DEFAULT_CONFIG = {
    "monitor_stocks": True,
    "monitor_options": True,
    "monitor_futures": True,
    "notify_order_submitted": True,
    "shortcuts": DEFAULT_SHORTCUTS,
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


def load_env_files(override=True):
    """Load shareable .env first, then secrets.env on top."""
    if os.path.exists(ENV_PATH):
        load_dotenv(ENV_PATH, override=override)
    if os.path.exists(SECRETS_PATH):
        load_dotenv(SECRETS_PATH, override=True)


def read_env_values():
    """Return merged values from .env and secrets.env for the settings UI."""
    values = {}
    if os.path.exists(ENV_PATH):
        values.update(dotenv_values(ENV_PATH) or {})
    if os.path.exists(SECRETS_PATH):
        values.update(dotenv_values(SECRETS_PATH) or {})
    return values


def write_env_file(path, config):
    with open(path, "w", encoding="utf-8") as f:
        for key, value in config.items():
            value = str(value).replace('"', '\\"')
            f.write(f'{key}="{value}"\n')


def save_env_and_secrets(all_config):
    """Split secrets into secrets.env and everything else into .env."""
    secrets = {key: all_config[key] for key in SECRET_KEYS if key in all_config}
    public = {key: value for key, value in all_config.items() if key not in SECRET_KEYS}
    write_env_file(ENV_PATH, public)
    write_env_file(SECRETS_PATH, secrets)
    load_env_files(override=True)


def _deep_merge_defaults(data):
    """Ensure required keys exist without wiping user values."""
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    if not isinstance(data, dict):
        return merged

    for key in ("monitor_stocks", "monitor_options", "monitor_futures", "notify_order_submitted"):
        if key in data:
            merged[key] = bool(data[key])

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

    return merged


def load_config():
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
    cleaned = _deep_merge_defaults(config)
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


def format_percentage_label(pct):
    if pct is None:
        return "n/a"
    return f"{pct}%"
