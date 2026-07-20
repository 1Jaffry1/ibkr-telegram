"""Telegram channel room open/close helpers (rename channel + remove rename notice)."""

import json
import os
import threading
import time

import requests

from config_store import load_config, load_env_files


def _token_and_chat():
    load_env_files(override=True)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    return token, chat_id


def _api(token, method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    response = requests.post(url, data=params, timeout=25)
    try:
        return response.json()
    except Exception:
        return {"ok": False, "description": response.text}


def room_settings(config=None):
    config = config or load_config()
    room = config.get("room") or {}
    return {
        "open_button": (room.get("open_button") or "OPEN ROOM").strip() or "OPEN ROOM",
        "close_button": (room.get("close_button") or "CLOSE ROOM").strip() or "CLOSE ROOM",
        "open_text": (room.get("open_text") or "ROOM OPEN").strip() or "ROOM OPEN",
        "closed_text": (room.get("closed_text") or "ROOM CLOSED").strip() or "ROOM CLOSED",
    }


def strip_room_status(title, open_text, closed_text):
    """Remove trailing room status suffix so we keep the base channel name."""
    title = (title or "").strip()
    for status in (open_text, closed_text):
        status = (status or "").strip()
        if not status:
            continue
        for sep in (f" - {status}", f" – {status}", f" — {status}", f"- {status}", f"-{status}"):
            if title.endswith(sep):
                return title[: -len(sep)].rstrip(" -–—")
    return title


def build_room_title(base_title, status_text):
    base = (base_title or "").strip() or "Channel"
    status = (status_text or "").strip()
    title = f"{base} - {status}" if status else base
    return title[:128]


def get_chat_title(token, chat_id):
    data = _api(token, "getChat", chat_id=chat_id)
    if not data.get("ok"):
        raise RuntimeError(data.get("description") or "getChat failed")
    return data["result"].get("title") or ""


def _is_title_change_update(update, chat_id):
    for key in ("channel_post", "message"):
        msg = update.get(key)
        if not msg:
            continue
        chat = msg.get("chat") or {}
        if str(chat.get("id")) != str(chat_id):
            continue
        if msg.get("new_chat_title"):
            return msg.get("message_id")
    return None


def purge_title_change_notices(token, chat_id, rounds=6, timeout=1):
    """
    Poll getUpdates and delete channel/group title-change service messages.
    Bot must be admin with can_delete_messages.
    Telegram always posts the notice; it cannot be blocked, only deleted.
    """
    deleted = 0
    offset = None
    for _ in range(rounds):
        params = {
            "timeout": timeout,
            "allowed_updates": json.dumps(["channel_post", "message"]),
        }
        if offset is not None:
            params["offset"] = offset
        data = _api(token, "getUpdates", **params)
        if not data.get("ok"):
            break
        updates = data.get("result") or []
        if not updates:
            time.sleep(0.35)
            continue
        for update in updates:
            update_id = update.get("update_id")
            if update_id is not None:
                offset = update_id + 1
            message_id = _is_title_change_update(update, chat_id)
            if message_id is None:
                continue
            del_result = _api(token, "deleteMessage", chat_id=chat_id, message_id=message_id)
            if del_result.get("ok"):
                deleted += 1
    return deleted


def set_room_state(is_open, config=None):
    """
    Rename channel to "{base} - ROOM OPEN/CLOSED" and delete the rename notice.
    Returns (ok, new_title, detail_message).
    """
    token, chat_id = _token_and_chat()
    if not token or not chat_id:
        return False, "", "Set Telegram bot token and chat ID in Settings first."

    settings = room_settings(config)
    status_text = settings["open_text"] if is_open else settings["closed_text"]

    try:
        current = get_chat_title(token, chat_id)
    except Exception as exc:
        return False, "", f"Could not read channel title: {exc}"

    base = strip_room_status(current, settings["open_text"], settings["closed_text"])
    new_title = build_room_title(base, status_text)

    if new_title == current:
        return True, new_title, "Channel already has this title."

    # disable_notification is not documented for setChatTitle; Telegram may ignore it.
    # Channel-wide mute before rename is not available to bots — only delete the notice after.
    result = _api(
        token,
        "setChatTitle",
        chat_id=chat_id,
        title=new_title,
        disable_notification="true",
    )
    if not result.get("ok"):
        desc = result.get("description") or "setChatTitle failed"
        return False, current, (
            f"{desc}\n\nBot needs admin rights: Change Channel Info + Delete Messages."
        )

    # Delete as fast as possible so fewer clients show the service-message notification.
    time.sleep(0.15)
    deleted = purge_title_change_notices(token, chat_id, rounds=10, timeout=1)
    if deleted:
        detail = f'Renamed to "{new_title}" and removed {deleted} rename notice(s).'
    else:
        detail = (
            f'Renamed to "{new_title}". '
            "Could not auto-delete the rename notice — ensure the bot can Delete Messages "
            "and is an admin in the channel.\n\n"
            "Note: Telegram does not let bots mute channel notifications before a rename; "
            "deleting the notice is the supported approach."
        )
    return True, new_title, detail


class TitleChangeCleaner:
    """Background poller that deletes title-change notices while the companion is open."""

    def __init__(self, status_callback=None):
        self.status_callback = status_callback
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _emit(self, message):
        if self.status_callback:
            try:
                self.status_callback(message)
            except Exception:
                pass

    def _run(self):
        offset = None
        while not self._stop.is_set():
            token, chat_id = _token_and_chat()
            if not token or not chat_id:
                self._stop.wait(5)
                continue
            params = {
                "timeout": 20,
                "allowed_updates": json.dumps(["channel_post", "message"]),
            }
            if offset is not None:
                params["offset"] = offset
            try:
                data = _api(token, "getUpdates", **params)
            except Exception:
                self._stop.wait(2)
                continue
            if not data.get("ok"):
                self._stop.wait(2)
                continue
            for update in data.get("result") or []:
                update_id = update.get("update_id")
                if update_id is not None:
                    offset = update_id + 1
                message_id = _is_title_change_update(update, chat_id)
                if message_id is None:
                    continue
                del_result = _api(token, "deleteMessage", chat_id=chat_id, message_id=message_id)
                if del_result.get("ok"):
                    self._emit("🧹 Removed channel rename notice")
