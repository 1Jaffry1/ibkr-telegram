"""Session / long-term trade summary counters and trade ID counter."""

import json
import os
import threading

from config_store import SUMMARY_PATH

DEFAULT_SUMMARY_MESSAGE = """📊 *SUMMARY*

*Trades taken:* `{trades}`
🟢 *Green:* `{green}`
🔴 *Red:* `{red}`"""

DEFAULT_LONG_TERM_SUMMARY_MESSAGE = """📊 *LONG-TERM SUMMARY*

*Trades taken:* `{trades}`
🟢 *Green:* `{green}`
🔴 *Red:* `{red}`"""

EMPTY_COUNTS = {"trades": 0, "green": 0, "red": 0}

DEFAULT_SUMMARY = {
    "session": dict(EMPTY_COUNTS),
    "long_term": dict(EMPTY_COUNTS),
    "trade_counter": 0,
}

_DIGIT_KEYCAPS = {
    "0": "0️⃣",
    "1": "1️⃣",
    "2": "2️⃣",
    "3": "3️⃣",
    "4": "4️⃣",
    "5": "5️⃣",
    "6": "6️⃣",
    "7": "7️⃣",
    "8": "8️⃣",
    "9": "9️⃣",
}

_lock = threading.Lock()


def _normalize_bucket(data):
    if not isinstance(data, dict):
        return dict(EMPTY_COUNTS)
    return {
        "trades": max(0, int(data.get("trades") or 0)),
        "green": max(0, int(data.get("green") or 0)),
        "red": max(0, int(data.get("red") or 0)),
    }


def _normalize(data):
    if not isinstance(data, dict):
        return json.loads(json.dumps(DEFAULT_SUMMARY))
    try:
        counter = max(0, int(data.get("trade_counter") or 0))
    except (TypeError, ValueError):
        counter = 0
    return {
        "session": _normalize_bucket(data.get("session")),
        "long_term": _normalize_bucket(data.get("long_term")),
        "trade_counter": counter,
    }


def format_cnt_emoji(n):
    """Turn 14 into 1️⃣4️⃣. Returns '' when n is missing or <= 0."""
    try:
        value = int(n)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return "".join(_DIGIT_KEYCAPS[d] for d in str(value))


TEXTBOX_PLACEHOLDER = "{textbox}"
TEXTBOX_MAX_LEN = 10


def message_uses_textbox(text):
    """True when a shortcut message includes the {textbox} placeholder."""
    return TEXTBOX_PLACEHOLDER in str(text or "")


def shortcuts_use_textbox(shortcuts):
    """True if any shortcut message uses {textbox}."""
    return any(message_uses_textbox(item.get("message", "")) for item in (shortcuts or []))


def apply_textbox_placeholder(text, user_text=None):
    """Replace {textbox} with up to 10 characters from the shortcut button."""
    if text is None:
        return ""
    text = str(text)
    if TEXTBOX_PLACEHOLDER not in text:
        return text
    value = str(user_text or "")[:TEXTBOX_MAX_LEN]
    return text.replace(TEXTBOX_PLACEHOLDER, value)


def apply_cnt_placeholder(text, cnt_emoji=None):
    """Replace {cnt} in a message. Other braces are left alone."""
    if text is None:
        return ""
    text = str(text)
    if "{cnt}" not in text:
        return text
    if cnt_emoji is None:
        cnt_emoji = current_cnt_emoji()
    return text.replace("{cnt}", cnt_emoji)


def load_summary():
    with _lock:
        if not os.path.exists(SUMMARY_PATH):
            data = json.loads(json.dumps(DEFAULT_SUMMARY))
            _write_unlocked(data)
            return data
        try:
            with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = json.loads(json.dumps(DEFAULT_SUMMARY))
        return _normalize(data)


def _write_unlocked(data):
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(_normalize(data), f, indent=2)
        f.write("\n")


def save_summary(data):
    with _lock:
        _write_unlocked(data)


def reset_summary(kind="session"):
    """Reset session or long_term counters. kind: 'session' | 'long_term'."""
    data = load_summary()
    key = "long_term" if kind == "long_term" else "session"
    data[key] = dict(EMPTY_COUNTS)
    save_summary(data)
    return data


def record_indicator(role):
    """
    Count a summary indicator from a mapped shortcut button.

    green → trades +1, green +1
    red   → trades +1, red +1
    close → trades +1 only
    """
    role = str(role or "").strip().lower()
    if role not in ("green", "red", "close"):
        return load_summary(), None

    data = load_summary()
    for key in ("session", "long_term"):
        bucket = data[key]
        bucket["trades"] += 1
        if role in ("green", "red"):
            bucket[role] += 1

    save_summary(data)
    return data, role


def _summary_template(kind="session"):
    if kind == "long_term":
        value = os.getenv("LONG_TERM_SUMMARY_MESSAGE")
        default = DEFAULT_LONG_TERM_SUMMARY_MESSAGE
    else:
        value = os.getenv("SUMMARY_MESSAGE")
        default = DEFAULT_SUMMARY_MESSAGE
    if value is None or not str(value).strip():
        return default
    return value


def _summary_context(kind="session"):
    data = load_summary()
    key = "long_term" if kind == "long_term" else "session"
    bucket = data[key]
    return {
        "trades": bucket["trades"],
        "green": bucket["green"],
        "red": bucket["red"],
        "cnt": current_cnt_emoji(),
    }


def format_summary_message(kind="session"):
    """Render the editable summary template from messages.env."""
    template = _summary_template(kind)
    context = _summary_context(kind)
    try:
        return template.format(**context)
    except (KeyError, ValueError):
        # Unknown placeholders are left alone; still fill known ones.
        message = template
        for key, value in context.items():
            message = message.replace("{" + key + "}", str(value))
        return message


def format_summary_preview(kind="session"):
    rendered = format_summary_message(kind)
    return f"{rendered}\n\nSend this to Telegram?"


def summary_label_text():
    data = load_summary()
    s = data["session"]
    lt = data["long_term"]
    return (
        f"Session — trades {s['trades']} · green {s['green']} · red {s['red']}   |   "
        f"Long-term — trades {lt['trades']} · green {lt['green']} · red {lt['red']}"
    )


def get_trade_counter():
    return int(load_summary().get("trade_counter") or 0)


def current_cnt_emoji():
    return format_cnt_emoji(get_trade_counter())


def increment_trade_counter():
    """Bump trade ID by 1. Returns (new_value, emoji)."""
    data = load_summary()
    data["trade_counter"] = int(data.get("trade_counter") or 0) + 1
    save_summary(data)
    value = data["trade_counter"]
    return value, format_cnt_emoji(value)


def reset_trade_counter():
    data = load_summary()
    data["trade_counter"] = 0
    save_summary(data)
    return data


def counter_label_text():
    value = get_trade_counter()
    emoji = format_cnt_emoji(value)
    if value <= 0:
        return "Trade ID: none yet  (press a mapped shortcut to start)"
    return f"Trade ID: {value}  {emoji}"
