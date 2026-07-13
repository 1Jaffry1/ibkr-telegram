"""
IBKR Trade Alerts — companion window + settings.

Run this file to open the always-on companion:
  Start/Stop monitoring, shortcut Telegram buttons, and Settings.
"""

import os
import platform
import tkinter as tk
from tkinter import ttk

from client import MonitorController, send_telegram_message, reload_env
from config_store import load_config, save_config, read_env_values, save_env_and_secrets


# --- Colors / theme ---------------------------------------------------------

COLORS = {
    "bg": "#F4F7FB",
    "surface": "#FFFFFF",
    "primary": "#1F6FEB",
    "primary_dark": "#1158C7",
    "success": "#1A7F37",
    "danger": "#CF222E",
    "warning": "#9A6700",
    "text": "#1F2328",
    "muted": "#57606A",
    "border": "#D0D7DE",
    "accent": "#DDF4FF",
    "log_bg": "#0D1117",
    "log_fg": "#E6EDF3",
    "log_ok": "#3FB950",
    "log_err": "#FF7B72",
    "log_info": "#58A6FF",
}

FIRST_USE_GUIDE = """FIRST-TIME SETUP GUIDE
======================

Do these steps once before monitoring trades.

1) START IBKR
   • Open IB Gateway (recommended) or Trader Workstation (TWS)
   • Log in (live or paper)

2) ENABLE THE API
   IB Gateway:
     Configure → Settings → API → Settings
   TWS:
     Edit → Global Configuration → API → Settings

   Required:
   ☑ Enable ActiveX and Socket Clients
   ☐ Read-Only API  (must be OFF if you need order events)
   • Socket port:
       Gateway paper 4002  |  Gateway live 4001
       TWS paper 7497      |  TWS live 7496
   • Trusted IPs: add 127.0.0.1 if prompted

3) MASTER / CLIENT ID = 0  (important)
   In the same API Settings page:
   • Set Master API Client ID to 0
     (or leave blank and connect this app with Client ID 0)

   In this app Settings → IBKR:
   • Client ID must be 0

   Why? Orders placed in TWS / Gateway / mobile are only
   visible to client ID 0. Other client IDs miss those trades.

4) TELEGRAM
   Settings → Telegram:
   • Bot Token from @BotFather
   • Chat / Channel ID
   • Click Test Telegram

5) OPTIONAL
   • Asset Types: choose stocks / options / futures
   • Percentages: set what 100% means (e.g. GLD = 8 contracts)
   • Turn off “submitted order” alerts if you only want fills
   • Customize shortcut buttons

6) RUN
   Companion window → Start Monitoring
   Keep IB Gateway/TWS open while monitoring.

Tips
---
• Paper vs live is only the port + which IBKR session you login to
• If no alerts appear: confirm Client ID 0 + Master API Client ID 0
• Activity log on the companion shows connection and trade events
• Cmd/Ctrl+Z undoes text edits; Cmd/Ctrl+Shift+Z (or Ctrl+Y) redoes
"""

MESSAGE_GUIDE = """MESSAGE TEMPLATE GUIDE

Use curly-brace variables. They are filled from each trade.

Common:
  {symbol}               Underlying / ticker
  {exchange}             Exchange
  {percentage}           Size vs your 100% baseline (e.g. 50%)
  {percentage_raw}       Same number without the % sign
  {quantity}             Raw shares / contracts (optional)
  {time}                 Execution time
  {account}              Account number
  {commission}           Commission
  {price}                Fill / limit price
  {contract_description} Human-readable contract
  {sec_type}             STK / OPT / FUT / ...

Submission-only:
  {action} {order_type} {limit_price} {status}

Fill-only:
  {side}                 BOUGHT / SOLD (mapped from IBKR BOT / SLD)

Options-only:
  {option_type} {strike} {expiry}

Futures-only:
  {expiry} {local_symbol} {multiplier} {trading_class}

Percentage example:
  If GLD options 100% = 8 contracts and you buy 4,
  {percentage} becomes 50%.

Baselines are set on the Percentages tab
(defaults per asset type + symbol exceptions).
"""

DEFAULT_ORDER_MESSAGE = """📝 *ORDER SUBMITTED*

*Symbol:* `{symbol}`
*Exchange:* `{exchange}`
*Action:* `{action}`
*Size:* `{percentage}` of full size
*Type:* `{order_type}`
*Price:* `{limit_price}`
*Status:* `{status}`"""

DEFAULT_ORDER_OPTION_MESSAGE = """📝 *OPTION ORDER SUBMITTED*

*Underlying:* `{symbol}`
*Contract:* `{contract_description}`
*Action:* `{action}`
*Size:* `{percentage}` of full size
*Type:* `{order_type}`
*Price:* `{limit_price}`
*Status:* `{status}`"""

DEFAULT_ORDER_FUTURE_MESSAGE = """📝 *FUTURES ORDER SUBMITTED*

*Symbol:* `{symbol}`
*Contract:* `{contract_description}`
*Expiry:* `{expiry}`
*Exchange:* `{exchange}`
*Action:* `{action}`
*Size:* `{percentage}` of full size
*Type:* `{order_type}`
*Price:* `{limit_price}`
*Status:* `{status}`"""

DEFAULT_TRADE_MESSAGE = """✅ *ORDER FILLED*

*Symbol:* `{symbol}`
*Exchange:* `{exchange}`
*Action:* `{side}`
*Size:* `{percentage}` of full size
*Price:* `${price}`
*Commission:* `${commission}`
*Time:* `{time}`
*Account:* `{account}`"""

DEFAULT_OPTION_MESSAGE = """✅ *OPTION ORDER FILLED*

*Underlying:* `{symbol}`
*Contract:* `{contract_description}`
*Type:* `{option_type}`
*Strike:* `${strike}`
*Expiry:* `{expiry}`
*Action:* `{side}`
*Size:* `{percentage}` of full size
*Price:* `${price}`
*Commission:* `${commission}`
*Time:* `{time}`
*Account:* `{account}`"""

DEFAULT_FUTURE_MESSAGE = """✅ *FUTURES ORDER FILLED*

*Symbol:* `{symbol}`
*Contract:* `{contract_description}`
*Expiry:* `{expiry}`
*Exchange:* `{exchange}`
*Action:* `{side}`
*Size:* `{percentage}` of full size
*Price:* `{price}`
*Commission:* `${commission}`
*Time:* `{time}`
*Account:* `{account}`"""


# --- UI helpers -------------------------------------------------------------

def apply_theme(root):
    """Use a colored clam theme instead of greyscale aqua defaults."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=COLORS["bg"])
    style.configure(".", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Card.TFrame", background=COLORS["surface"])
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"])
    style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 16, "bold"))
    style.configure("Heading.TLabel", background=COLORS["bg"], foreground=COLORS["primary"], font=("Segoe UI", 13, "bold"))
    style.configure("Status.Idle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"])
    style.configure("Status.Run.TLabel", background=COLORS["bg"], foreground=COLORS["success"], font=("Segoe UI", 10, "bold"))
    style.configure("Status.Stop.TLabel", background=COLORS["bg"], foreground=COLORS["warning"], font=("Segoe UI", 10, "bold"))
    style.configure("TLabelframe", background=COLORS["bg"], foreground=COLORS["primary"])
    style.configure("TLabelframe.Label", background=COLORS["bg"], foreground=COLORS["primary"], font=("Segoe UI", 10, "bold"))
    style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=COLORS["border"], foreground=COLORS["text"], padding=(12, 6))
    style.map("TNotebook.Tab", background=[("selected", COLORS["primary"])], foreground=[("selected", "#FFFFFF")])
    style.configure("TButton", background=COLORS["primary"], foreground="#FFFFFF", padding=(10, 6), borderwidth=0)
    style.map("TButton", background=[("active", COLORS["primary_dark"]), ("disabled", COLORS["border"])], foreground=[("disabled", COLORS["muted"])])
    style.configure("Success.TButton", background=COLORS["success"], foreground="#FFFFFF")
    style.map("Success.TButton", background=[("active", "#146C2E"), ("disabled", COLORS["border"])])
    style.configure("Danger.TButton", background=COLORS["danger"], foreground="#FFFFFF")
    style.map("Danger.TButton", background=[("active", "#A40E26"), ("disabled", COLORS["border"])])
    style.configure("Secondary.TButton", background="#EAEEF2", foreground=COLORS["text"])
    style.map("Secondary.TButton", background=[("active", COLORS["border"])])
    style.configure("TEntry", fieldbackground=COLORS["surface"], foreground=COLORS["text"])
    style.configure("TCheckbutton", background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("TCombobox", fieldbackground=COLORS["surface"], foreground=COLORS["text"])
    style.configure("Vertical.TScrollbar", background=COLORS["border"])


def center_on_parent(window, parent, width=None, height=None):
    parent.update_idletasks()
    window.update_idletasks()
    if width is None:
        width = max(window.winfo_reqwidth(), 360)
    if height is None:
        height = max(window.winfo_reqheight(), 180)
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    pw = max(parent.winfo_width(), 1)
    ph = max(parent.winfo_height(), 1)
    x = px + max((pw - width) // 2, 0)
    y = py + max((ph - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")


def _dialog(parent, title, message, kind="info", yes_no=False):
    """Modal dialog positioned over the parent window."""
    parent = parent or tk._default_root
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.configure(bg=COLORS["surface"])
    dialog.resizable(False, False)

    accent = {
        "info": COLORS["primary"],
        "error": COLORS["danger"],
        "success": COLORS["success"],
        "warning": COLORS["warning"],
    }.get(kind, COLORS["primary"])

    result = {"value": False}

    header = tk.Frame(dialog, bg=accent, height=8)
    header.pack(fill="x")

    body = tk.Frame(dialog, bg=COLORS["surface"], padx=18, pady=16)
    body.pack(fill="both", expand=True)
    tk.Label(
        body,
        text=title,
        bg=COLORS["surface"],
        fg=COLORS["text"],
        font=("Segoe UI", 12, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(0, 8))
    tk.Label(
        body,
        text=message,
        bg=COLORS["surface"],
        fg=COLORS["text"],
        justify="left",
        wraplength=380,
        anchor="w",
    ).pack(fill="x")

    buttons = tk.Frame(body, bg=COLORS["surface"])
    buttons.pack(fill="x", pady=(16, 0))

    def close(value=False):
        result["value"] = value
        dialog.destroy()

    if yes_no:
        ttk.Button(buttons, text="Cancel", style="Secondary.TButton", command=lambda: close(False)).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Yes", style="Success.TButton", command=lambda: close(True)).pack(side="right")
    else:
        ttk.Button(buttons, text="OK", style="Success.TButton", command=lambda: close(True)).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
    center_on_parent(dialog, parent, width=440, height=220)
    parent.wait_window(dialog)
    return result["value"]


def show_info(parent, title, message):
    return _dialog(parent, title, message, kind="info")


def show_error(parent, title, message):
    return _dialog(parent, title, message, kind="error")


def show_success(parent, title, message):
    return _dialog(parent, title, message, kind="success")


def ask_yes_no(parent, title, message):
    return _dialog(parent, title, message, kind="warning", yes_no=True)


def enable_text_undo(widget):
    """Enable undo/redo for Text widgets (Cmd/Ctrl+Z, Cmd/Ctrl+Shift+Z, Ctrl+Y)."""
    try:
        widget.configure(undo=True, maxundo=-1, autoseparators=True)
    except tk.TclError:
        return

    def undo_event(event):
        try:
            widget.edit_undo()
        except tk.TclError:
            pass
        return "break"

    def redo_event(event):
        try:
            widget.edit_redo()
        except tk.TclError:
            pass
        return "break"

    for seq in ("<Control-z>", "<Control-Z>", "<Command-z>", "<Command-Z>"):
        widget.bind(seq, undo_event)
    for seq in ("<Control-y>", "<Control-Y>", "<Control-Shift-Z>", "<Command-Shift-Z>", "<Command-y>", "<Command-Y>"):
        widget.bind(seq, redo_event)


def enable_entry_undo(entry):
    """Simple undo/redo stack for ttk/tk Entry widgets."""
    history = [entry.get()]
    index = {"i": 0}
    applying = {"flag": False}

    def snapshot(event=None):
        if applying["flag"]:
            return
        value = entry.get()
        if history[index["i"]] == value:
            return
        history[:] = history[: index["i"] + 1]
        history.append(value)
        index["i"] = len(history) - 1
        if len(history) > 100:
            history.pop(0)
            index["i"] -= 1

    def undo(event=None):
        if index["i"] <= 0:
            return "break"
        index["i"] -= 1
        applying["flag"] = True
        entry.delete(0, "end")
        entry.insert(0, history[index["i"]])
        applying["flag"] = False
        return "break"

    def redo(event=None):
        if index["i"] >= len(history) - 1:
            return "break"
        index["i"] += 1
        applying["flag"] = True
        entry.delete(0, "end")
        entry.insert(0, history[index["i"]])
        applying["flag"] = False
        return "break"

    entry.bind("<KeyRelease>", snapshot)
    entry.bind("<<Paste>>", lambda e: entry.after_idle(snapshot))
    for seq in ("<Control-z>", "<Control-Z>", "<Command-z>", "<Command-Z>"):
        entry.bind(seq, undo)
    for seq in ("<Control-y>", "<Control-Y>", "<Control-Shift-Z>", "<Command-Shift-Z>", "<Command-y>", "<Command-Y>"):
        entry.bind(seq, redo)


def make_text(parent, **kwargs):
    kwargs.setdefault("bg", COLORS["surface"])
    kwargs.setdefault("fg", COLORS["text"])
    kwargs.setdefault("insertbackground", COLORS["primary"])
    kwargs.setdefault("relief", "solid")
    kwargs.setdefault("borderwidth", 1)
    kwargs.setdefault("highlightthickness", 1)
    kwargs.setdefault("highlightbackground", COLORS["border"])
    kwargs.setdefault("highlightcolor", COLORS["primary"])
    widget = tk.Text(parent, **kwargs)
    enable_text_undo(widget)
    return widget


def make_entry(parent, **kwargs):
    entry = ttk.Entry(parent, **kwargs)
    enable_entry_undo(entry)
    return entry


class HelpWindow(tk.Toplevel):
    def __init__(self, master, on_close=None, on_open_settings=None):
        super().__init__(master)
        self.title("Setup Guide")
        self.on_close_cb = on_close
        self.on_open_settings = on_open_settings
        self.configure(bg=COLORS["bg"])
        self.transient(master)

        header = tk.Frame(self, bg=COLORS["primary"], padx=16, pady=12)
        header.pack(fill="x")
        tk.Label(header, text="First-Use Setup Guide", bg=COLORS["primary"], fg="#FFFFFF", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(header, text="IBKR API + Telegram checklist before monitoring", bg=COLORS["primary"], fg="#DDF4FF").pack(anchor="w")

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        text = make_text(body, height=28, width=78, wrap="word")
        text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(body, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", FIRST_USE_GUIDE)
        text.config(state="disabled")

        footer = ttk.Frame(self, padding=12)
        footer.pack(fill="x")
        ttk.Button(footer, text="Open Settings", style="Success.TButton", command=self._open_settings).pack(side="left")
        ttk.Button(footer, text="Got it", command=self._close).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close)
        center_on_parent(self, master, width=720, height=640)

    def _open_settings(self):
        callback = self.on_open_settings
        self._close()
        if callback:
            callback()

    def _close(self):
        if self.on_close_cb:
            self.on_close_cb()
        self.destroy()


class SettingsWindow(tk.Toplevel):
    def __init__(self, master, on_saved=None):
        super().__init__(master)
        self.title("IBKR Trade Alerts - Settings")
        self.minsize(700, 760)
        self.configure(bg=COLORS["bg"])
        self.transient(master)
        self.on_saved = on_saved
        self.app_config = load_config()
        self.load_env_file()
        self.exception_rows = []
        self.shortcut_rows = []

        button_frame = ttk.Frame(self)
        button_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        ttk.Button(button_frame, text="💾 Save", style="Success.TButton", command=self.save_config).pack(side="left", padx=5)
        ttk.Button(button_frame, text="📤 Test Telegram", command=self.test_telegram).pack(side="left", padx=5)
        ttk.Button(button_frame, text="❓ Help", style="Secondary.TButton", command=self.open_help).pack(side="left", padx=5)
        ttk.Button(button_frame, text="✕ Close", style="Secondary.TButton", command=self.destroy).pack(side="right", padx=5)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        self.create_telegram_tab()
        self.create_ibkr_tab()
        self.create_assets_tab()
        self.create_percentages_tab()
        self.create_shortcuts_tab()
        self.create_messages_tab()

        center_on_parent(self, master, width=740, height=780)

    def open_help(self):
        HelpWindow(self)

    def load_env_file(self):
        self.env_vars = read_env_values()

    def _env_bool(self, key, default=False):
        value = self.env_vars.get(key)
        if value is None:
            return default
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

    def _create_scrollable_tab(self, tab_title):
        outer = ttk.Frame(self.notebook)
        self.notebook.add(outer, text=tab_title)
        canvas = tk.Canvas(outer, highlightthickness=0, bg=COLORS["bg"])
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas, padding="16")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return frame

    def create_telegram_tab(self):
        frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(frame, text="Telegram")
        ttk.Label(frame, text="Telegram Bot Configuration", style="Heading.TLabel").grid(row=0, column=0, columnspan=2, pady=10, sticky="w")
        ttk.Label(
            frame,
            text="Tokens are saved to secrets.env (gitignored). Connection settings stay in .env. Templates stay in messages.env.",
            style="Muted.TLabel",
            wraplength=560,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="Bot Token:").grid(row=2, column=0, sticky="w", pady=5)
        self.telegram_token = make_entry(frame, width=52, show="*")
        self.telegram_token.insert(0, self.env_vars.get('TELEGRAM_BOT_TOKEN', ''))
        self.telegram_token.grid(row=2, column=1, padx=10)
        ttk.Label(frame, text="Chat/Channel ID:").grid(row=3, column=0, sticky="w", pady=5)
        self.telegram_chat_id = make_entry(frame, width=52)
        self.telegram_chat_id.insert(0, self.env_vars.get('TELEGRAM_CHAT_ID', ''))
        self.telegram_chat_id.grid(row=3, column=1, padx=10)

    def create_ibkr_tab(self):
        frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(frame, text="IBKR")
        ttk.Label(frame, text="IBKR Connection Settings", style="Heading.TLabel").grid(row=0, column=0, columnspan=2, pady=10, sticky="w")

        ttk.Label(frame, text="Host:").grid(row=1, column=0, sticky="w", pady=5)
        self.ibkr_host = make_entry(frame, width=40)
        self.ibkr_host.insert(0, self.env_vars.get('IBKR_HOST', '127.0.0.1'))
        self.ibkr_host.grid(row=1, column=1, padx=10)

        ttk.Label(frame, text="Port:").grid(row=2, column=0, sticky="w", pady=5)
        self.ibkr_port = make_entry(frame, width=40)
        self.ibkr_port.insert(0, self.env_vars.get('IBKR_PORT', '7496'))
        self.ibkr_port.grid(row=2, column=1, padx=10)

        ttk.Label(frame, text="Client ID:").grid(row=3, column=0, sticky="w", pady=5)
        self.ibkr_client_id = make_entry(frame, width=40)
        self.ibkr_client_id.insert(0, self.env_vars.get('IBKR_CLIENT_ID', '0') or '0')
        self.ibkr_client_id.grid(row=3, column=1, padx=10)

        self.auto_stop_enabled = tk.BooleanVar(value=self._env_bool('AUTO_STOP_ENABLED', default=True))
        ttk.Checkbutton(frame, text="Enable Auto-Stop", variable=self.auto_stop_enabled, command=self._toggle_auto_stop_fields).grid(row=4, column=0, columnspan=2, sticky="w", pady=5)

        ttk.Label(frame, text="Auto-Stop Time (HH:MM):").grid(row=5, column=0, sticky="w", pady=5)
        self.stop_time = make_entry(frame, width=40)
        self.stop_time.insert(0, self.env_vars.get('STOP_TIME', '16:00') or '16:00')
        self.stop_time.grid(row=5, column=1, padx=10)
        self._toggle_auto_stop_fields()

        help_box = make_text(frame, height=9, width=70, wrap="word")
        help_box.insert("1.0", "Gateway ports: 4001 live / 4002 paper\nTWS ports: 7496 live / 7497 paper\nUse Client ID 0 + Master API Client ID 0 to receive manual orders.\nClick Help for the full first-use checklist.")
        help_box.config(state="disabled")
        help_box.grid(row=6, column=0, columnspan=2, pady=16, sticky="w")

    def _toggle_auto_stop_fields(self):
        self.stop_time.config(state="normal" if self.auto_stop_enabled.get() else "disabled")

    def create_assets_tab(self):
        frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(frame, text="Asset Types")
        ttk.Label(frame, text="Monitor These Markets", style="Heading.TLabel").pack(anchor="w", pady=10)
        ttk.Label(frame, text="Disable a type to skip Telegram alerts for that market.", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))

        self.monitor_stocks = tk.BooleanVar(value=self.app_config.get("monitor_stocks", True))
        self.monitor_options = tk.BooleanVar(value=self.app_config.get("monitor_options", True))
        self.monitor_futures = tk.BooleanVar(value=self.app_config.get("monitor_futures", True))
        self.notify_order_submitted = tk.BooleanVar(value=self.app_config.get("notify_order_submitted", True))

        ttk.Checkbutton(frame, text="Stocks", variable=self.monitor_stocks).pack(anchor="w", pady=4)
        ttk.Checkbutton(frame, text="Options (including futures options)", variable=self.monitor_options).pack(anchor="w", pady=4)
        ttk.Checkbutton(frame, text="Futures", variable=self.monitor_futures).pack(anchor="w", pady=4)

        ttk.Separator(frame).pack(fill="x", pady=16)
        ttk.Label(frame, text="Order Alerts", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Checkbutton(
            frame,
            text="Send alerts when orders are submitted",
            variable=self.notify_order_submitted,
        ).pack(anchor="w", pady=4)
        ttk.Label(
            frame,
            text="Turn this off to only receive filled-order messages.",
            style="Muted.TLabel",
            wraplength=560,
        ).pack(anchor="w", pady=(4, 0))

    def create_percentages_tab(self):
        frame = self._create_scrollable_tab("Percentages")
        ttk.Label(frame, text="100% Size Baselines", style="Heading.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=8)
        ttk.Label(
            frame,
            text="Set what 100% means for each asset type. Add symbol exceptions (e.g. GLD options = 8 contracts).",
            style="Muted.TLabel",
            wraplength=640,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 12))

        defaults = self.app_config["percentages"]["defaults"]
        self.default_vars = {}
        row = 2
        for asset, title in (("stock", "Stocks default"), ("option", "Options default"), ("future", "Futures default")):
            ttk.Label(frame, text=title, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w", pady=6)
            unit_var = tk.StringVar(value=defaults[asset]["unit"])
            value_var = tk.StringVar(value=str(defaults[asset]["value"]))
            self.default_vars[asset] = {"unit": unit_var, "value": value_var}
            unit_box = ttk.Combobox(frame, textvariable=unit_var, values=["quantity", "dollars"], width=12, state="readonly")
            unit_box.grid(row=row, column=1, padx=6)
            value_entry = make_entry(frame, textvariable=value_var, width=12)
            value_entry.grid(row=row, column=2, padx=6)
            ttk.Label(frame, text="quantity = shares/contracts", style="Muted.TLabel").grid(row=row, column=3, sticky="w")
            row += 1

        ttk.Separator(frame).grid(row=row, column=0, columnspan=4, sticky="ew", pady=12)
        row += 1
        ttk.Label(frame, text="Symbol Exceptions", style="Heading.TLabel").grid(row=row, column=0, columnspan=4, sticky="w")
        row += 1

        header = ttk.Frame(frame)
        header.grid(row=row, column=0, columnspan=4, sticky="ew", pady=4)
        for i, text in enumerate(("Symbol", "Asset", "Unit", "100% Value", "")):
            ttk.Label(header, text=text, width=12 if i < 4 else 6).grid(row=0, column=i, padx=3)
        row += 1

        self.exceptions_frame = ttk.Frame(frame)
        self.exceptions_frame.grid(row=row, column=0, columnspan=4, sticky="ew")
        row += 1

        ttk.Button(frame, text="➕ Add Exception", style="Secondary.TButton", command=self._add_exception_row).grid(row=row, column=0, sticky="w", pady=8)

        for item in self.app_config["percentages"].get("exceptions", []):
            self._add_exception_row(item)

    def _add_exception_row(self, data=None):
        data = data or {"symbol": "", "asset": "any", "unit": "quantity", "value": ""}
        row_frame = ttk.Frame(self.exceptions_frame)
        row_frame.pack(fill="x", pady=2)

        symbol_var = tk.StringVar(value=data.get("symbol", ""))
        asset_var = tk.StringVar(value=data.get("asset", "any"))
        unit_var = tk.StringVar(value=data.get("unit", "quantity"))
        value_var = tk.StringVar(value=str(data.get("value", "")))

        make_entry(row_frame, textvariable=symbol_var, width=12).grid(row=0, column=0, padx=3)
        ttk.Combobox(row_frame, textvariable=asset_var, values=["any", "stock", "option", "future"], width=10, state="readonly").grid(row=0, column=1, padx=3)
        ttk.Combobox(row_frame, textvariable=unit_var, values=["quantity", "dollars"], width=10, state="readonly").grid(row=0, column=2, padx=3)
        make_entry(row_frame, textvariable=value_var, width=12).grid(row=0, column=3, padx=3)

        row_data = {"frame": row_frame, "symbol": symbol_var, "asset": asset_var, "unit": unit_var, "value": value_var}

        def remove():
            row_frame.destroy()
            self.exception_rows.remove(row_data)

        ttk.Button(row_frame, text="✕", width=3, style="Danger.TButton", command=remove).grid(row=0, column=4, padx=3)
        self.exception_rows.append(row_data)

    def create_shortcuts_tab(self):
        frame = self._create_scrollable_tab("Shortcuts")
        ttk.Label(frame, text="Companion Shortcut Buttons", style="Heading.TLabel").pack(anchor="w", pady=8)
        ttk.Label(frame, text="These appear on the companion window and send a Telegram message when clicked.", style="Muted.TLabel", wraplength=640).pack(anchor="w", pady=(0, 10))

        self.shortcuts_frame = ttk.Frame(frame)
        self.shortcuts_frame.pack(fill="x")
        ttk.Button(frame, text="➕ Add Shortcut", style="Secondary.TButton", command=self._add_shortcut_row).pack(anchor="w", pady=8)

        for item in self.app_config.get("shortcuts", []):
            self._add_shortcut_row(item)
        if not self.shortcut_rows:
            self._add_shortcut_row()

    def _add_shortcut_row(self, data=None):
        data = data or {"id": "", "label": "", "message": ""}
        row_frame = ttk.LabelFrame(self.shortcuts_frame, text="Shortcut", padding=8)
        row_frame.pack(fill="x", pady=6)

        label_var = tk.StringVar(value=data.get("label", ""))
        id_value = data.get("id") or ""

        ttk.Label(row_frame, text="Button label:").grid(row=0, column=0, sticky="w")
        make_entry(row_frame, textvariable=label_var, width=28).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(row_frame, text="Telegram message:").grid(row=1, column=0, sticky="nw", pady=4)
        msg_box = make_text(row_frame, height=3, width=55, wrap="word")
        msg_box.insert("1.0", data.get("message", ""))
        msg_box.grid(row=1, column=1, sticky="w", padx=6, pady=4)

        row_data = {"frame": row_frame, "id": id_value, "label": label_var, "message_box": msg_box}

        def remove():
            row_frame.destroy()
            self.shortcut_rows.remove(row_data)

        ttk.Button(row_frame, text="Remove", style="Danger.TButton", command=remove).grid(row=0, column=2, padx=6)
        self.shortcut_rows.append(row_data)

    def create_messages_tab(self):
        frame = self._create_scrollable_tab("Messages")
        ttk.Label(frame, text="Message Templates", style="Heading.TLabel").grid(row=0, column=0, sticky="w", pady=8)

        guide = make_text(frame, height=14, width=78, wrap="word")
        guide.insert("1.0", MESSAGE_GUIDE)
        guide.config(state="disabled")
        guide.grid(row=1, column=0, sticky="ew", pady=6)

        templates = [
            ("Order Submitted (Stock)", "order_message", "ORDER_MESSAGE", DEFAULT_ORDER_MESSAGE, 6),
            ("Order Submitted (Option)", "order_option_message", "ORDER_OPTION_MESSAGE", DEFAULT_ORDER_OPTION_MESSAGE, 7),
            ("Order Submitted (Futures)", "order_future_message", "ORDER_FUTURE_MESSAGE", DEFAULT_ORDER_FUTURE_MESSAGE, 7),
            ("Order Filled (Stock)", "trade_message", "TRADE_MESSAGE", DEFAULT_TRADE_MESSAGE, 6),
            ("Order Filled (Option)", "option_message", "OPTION_MESSAGE", DEFAULT_OPTION_MESSAGE, 7),
            ("Order Filled (Futures)", "future_message", "FUTURE_MESSAGE", DEFAULT_FUTURE_MESSAGE, 7),
        ]

        row = 2
        for title, attr, env_key, default, height in templates:
            ttk.Label(frame, text=title, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w", pady=(10, 2))
            row += 1
            box = make_text(frame, height=height, width=78, wrap="word")
            box.insert("1.0", self.env_vars.get(env_key) or default)
            box.grid(row=row, column=0, sticky="ew", pady=2)
            setattr(self, attr, box)
            row += 1

        ttk.Label(frame, text="Connected Message:", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w", pady=(10, 2))
        row += 1
        self.connected_message = make_entry(frame, width=78)
        self.connected_message.insert(0, self.env_vars.get('CONNECTED_MESSAGE') or '✅ Connected to IBKR. Ready for trades.')
        self.connected_message.grid(row=row, column=0, sticky="ew")
        row += 1

        ttk.Label(frame, text="Market Closed Message:", font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w", pady=(10, 2))
        row += 1
        self.closed_message = make_entry(frame, width=78)
        self.closed_message.insert(0, self.env_vars.get('CLOSED_MESSAGE') or '📊 Market closed. Trade monitor stopping.')
        self.closed_message.grid(row=row, column=0, sticky="ew")

    def save_config(self):
        if not self.telegram_token.get().strip() or not self.telegram_chat_id.get().strip():
            show_error(self, "Error", "Telegram Bot Token and Chat ID are required!")
            return
        if not self.connected_message.get().strip() or not self.closed_message.get().strip():
            show_error(self, "Error", "Connected and Market Closed messages cannot be empty.")
            return

        if self.auto_stop_enabled.get():
            try:
                hour, minute = map(int, self.stop_time.get().strip().split(':'))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except ValueError:
                show_error(self, "Error", "Auto-stop time must be HH:MM.")
                return

        defaults = {}
        for asset, vars_map in self.default_vars.items():
            try:
                value = float(vars_map["value"].get())
                if value <= 0:
                    raise ValueError
            except ValueError:
                show_error(self, "Error", f"Invalid default value for {asset}.")
                return
            defaults[asset] = {"unit": vars_map["unit"].get(), "value": value}

        exceptions = []
        for row in self.exception_rows:
            symbol = row["symbol"].get().strip().upper()
            if not symbol:
                continue
            try:
                value = float(row["value"].get())
                if value <= 0:
                    raise ValueError
            except ValueError:
                show_error(self, "Error", f"Invalid exception value for {symbol}.")
                return
            exceptions.append({
                "symbol": symbol,
                "asset": row["asset"].get(),
                "unit": row["unit"].get(),
                "value": value,
            })

        shortcuts = []
        for row in self.shortcut_rows:
            label = row["label"].get().strip()
            message = row["message_box"].get("1.0", "end-1c").strip()
            if not label and not message:
                continue
            if not label or not message:
                show_error(self, "Error", "Each shortcut needs both a label and a message.")
                return
            shortcuts.append({
                "id": row["id"] or label.lower().replace(" ", "_"),
                "label": label,
                "message": message,
            })
        if not shortcuts:
            show_error(self, "Error", "Add at least one shortcut, or keep the defaults.")
            return

        env_config = {
            'TELEGRAM_BOT_TOKEN': self.telegram_token.get().strip(),
            'TELEGRAM_CHAT_ID': self.telegram_chat_id.get().strip(),
            'IBKR_HOST': self.ibkr_host.get().strip(),
            'IBKR_PORT': self.ibkr_port.get().strip(),
            'IBKR_CLIENT_ID': self.ibkr_client_id.get().strip() or '0',
            'AUTO_STOP_ENABLED': 'true' if self.auto_stop_enabled.get() else 'false',
            'STOP_TIME': self.stop_time.get().strip(),
            'ORDER_MESSAGE': self.order_message.get("1.0", "end-1c"),
            'ORDER_OPTION_MESSAGE': self.order_option_message.get("1.0", "end-1c"),
            'ORDER_FUTURE_MESSAGE': self.order_future_message.get("1.0", "end-1c"),
            'TRADE_MESSAGE': self.trade_message.get("1.0", "end-1c"),
            'OPTION_MESSAGE': self.option_message.get("1.0", "end-1c"),
            'FUTURE_MESSAGE': self.future_message.get("1.0", "end-1c"),
            'CONNECTED_MESSAGE': self.connected_message.get(),
            'CLOSED_MESSAGE': self.closed_message.get(),
        }

        existing = load_config()
        app_config = {
            "monitor_stocks": self.monitor_stocks.get(),
            "monitor_options": self.monitor_options.get(),
            "monitor_futures": self.monitor_futures.get(),
            "notify_order_submitted": self.notify_order_submitted.get(),
            "seen_setup_guide": existing.get("seen_setup_guide", False),
            "shortcuts": shortcuts,
            "percentages": {
                "defaults": defaults,
                "exceptions": exceptions,
            },
        }

        try:
            save_env_and_secrets(env_config)
            save_config(app_config)
            reload_env()
            show_success(
                self,
                "Success",
                "Settings saved.\nConnection → .env\nMessages → messages.env\nSecrets → secrets.env",
            )
            if self.on_saved:
                self.on_saved()
        except Exception as exc:
            show_error(self, "Error", f"Failed to save: {exc}")

    def test_telegram(self):
        import requests
        token = self.telegram_token.get().strip()
        chat_id = self.telegram_chat_id.get().strip()
        if not token or not chat_id:
            show_error(self, "Error", "Enter Bot Token and Chat ID first.")
            return
        try:
            response = requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                data={'chat_id': chat_id, 'text': '✅ Test message from IBKR Trade Alerts!', 'parse_mode': 'Markdown'},
                timeout=5,
            )
            if response.status_code == 200:
                show_success(self, "Success", "Test message sent.")
            else:
                show_error(self, "Error", f"Failed: {response.status_code}\n{response.text}")
        except Exception as exc:
            show_error(self, "Error", f"Connection error: {exc}")


class CompanionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("IBKR Trade Alerts")
        self.root.minsize(460, 580)
        self.root.geometry("500x620")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root._companion_app = self

        apply_theme(root)

        self.controller = MonitorController(status_callback=self._queue_status)
        self._status_queue = []
        self.settings_window = None
        self.help_window = None
        self.app_config = load_config()

        header = tk.Frame(root, bg=COLORS["primary"], padx=16, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="IBKR Trade Alerts", bg=COLORS["primary"], fg="#FFFFFF", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        self.status_label = tk.Label(header, text="Status: Idle", bg=COLORS["primary"], fg="#DDF4FF")
        self.status_label.pack(anchor="w", pady=(4, 0))

        controls = ttk.Frame(root, padding=12)
        controls.pack(fill="x")
        self.start_btn = ttk.Button(controls, text="▶ Start Monitoring", style="Success.TButton", command=self.start_monitoring)
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ttk.Button(controls, text="⏹ Stop", style="Danger.TButton", command=self.stop_monitoring, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="❓ Help", style="Secondary.TButton", command=self.open_help).pack(side="right")
        ttk.Button(controls, text="⚙ Settings", command=self.open_settings).pack(side="right", padx=(0, 8))

        shortcuts_wrap = ttk.LabelFrame(root, text="Shortcuts", padding=12)
        shortcuts_wrap.pack(fill="x", padx=12, pady=8)
        self.shortcuts_container = ttk.Frame(shortcuts_wrap)
        self.shortcuts_container.pack(fill="x")
        self.refresh_shortcuts()

        log_wrap = ttk.LabelFrame(root, text="Activity", padding=8)
        log_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log = tk.Text(
            log_wrap,
            height=16,
            wrap="word",
            state="disabled",
            bg=COLORS["log_bg"],
            fg=COLORS["log_fg"],
            insertbackground=COLORS["log_fg"],
            relief="flat",
            padx=8,
            pady=8,
        )
        self.log.pack(side="left", fill="both", expand=True)
        self.log.tag_configure("ok", foreground=COLORS["log_ok"])
        self.log.tag_configure("err", foreground=COLORS["log_err"])
        self.log.tag_configure("info", foreground=COLORS["log_info"])
        scroll = ttk.Scrollbar(log_wrap, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)

        self.root.after(200, self._drain_status_queue)
        self.append_log("Companion ready. Open Help for first-use IBKR setup, then Start Monitoring.", "info")
        self.root.after(400, self._maybe_show_first_use_guide)

    def _maybe_show_first_use_guide(self):
        cfg = load_config()
        if not cfg.get("seen_setup_guide", False):
            self.open_help(mark_seen=True)

    def open_help(self, mark_seen=False):
        if self.help_window and self.help_window.winfo_exists():
            self.help_window.lift()
            return

        def on_close():
            if mark_seen:
                cfg = load_config()
                cfg["seen_setup_guide"] = True
                save_config(cfg)

        def open_settings_from_help():
            if mark_seen:
                cfg = load_config()
                cfg["seen_setup_guide"] = True
                save_config(cfg)
            self.open_settings()

        self.help_window = HelpWindow(
            self.root,
            on_close=on_close,
            on_open_settings=open_settings_from_help,
        )

    def refresh_shortcuts(self):
        for child in self.shortcuts_container.winfo_children():
            child.destroy()
        self.app_config = load_config()
        shortcuts = self.app_config.get("shortcuts") or []
        if not shortcuts:
            ttk.Label(self.shortcuts_container, text="No shortcuts configured.", style="Muted.TLabel").pack(anchor="w")
            return
        for item in shortcuts:
            ttk.Button(
                self.shortcuts_container,
                text=item.get("label", "Shortcut"),
                command=lambda msg=item.get("message", ""): self.send_shortcut(msg),
            ).pack(fill="x", pady=3)

    def send_shortcut(self, message):
        reload_env()
        if not os.getenv('TELEGRAM_BOT_TOKEN') or not os.getenv('TELEGRAM_CHAT_ID'):
            show_error(self.root, "Error", "Set Telegram credentials in Settings first.")
            return
        message_id = send_telegram_message(message)
        if message_id:
            self.append_log(f"Shortcut sent: {message.splitlines()[0]}", "ok")
        else:
            self.append_log("Failed to send shortcut message.", "err")
            show_error(self.root, "Error", "Failed to send Telegram message.")

    def open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        self.settings_window = SettingsWindow(self.root, on_saved=self.refresh_shortcuts)

    def start_monitoring(self):
        reload_env()
        if not os.getenv('TELEGRAM_BOT_TOKEN') or not os.getenv('TELEGRAM_CHAT_ID'):
            show_error(self.root, "Error", "Set Telegram credentials in Settings first.")
            return
        if self.controller.start():
            self.status_label.config(text="Status: Monitoring")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.append_log("Starting monitor...", "info")
        else:
            show_info(self.root, "Info", "Monitor is already running.")

    def stop_monitoring(self):
        self.controller.stop()
        self.status_label.config(text="Status: Stopping...")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.append_log("Stop requested...", "info")

    def _queue_status(self, message):
        self._status_queue.append(message)

    def _drain_status_queue(self):
        while self._status_queue:
            message = self._status_queue.pop(0)
            tag = "info"
            lower = message.lower()
            if "✅" in message or "sent" in lower or "connected" in lower:
                tag = "ok"
            elif "❌" in message or "failed" in lower or "error" in lower:
                tag = "err"
            self.append_log(message, tag)
            if "Monitoring stopped" in message or "Monitor error" in message:
                self.status_label.config(text="Status: Idle")
                self.start_btn.config(state="normal")
                self.stop_btn.config(state="disabled")
            elif "Connected to IBKR" in message:
                self.status_label.config(text="Status: Connected")
        self.root.after(200, self._drain_status_queue)

    def append_log(self, message, tag="info"):
        self.log.config(state="normal")
        self.log.insert("end", message + "\n", tag)
        self.log.see("end")
        self.log.config(state="disabled")

    def on_close(self):
        if self.controller.is_running:
            if not ask_yes_no(self.root, "Quit", "Monitoring is running. Stop and quit?"):
                return
            self.controller.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    if platform.system() == "Darwin":
        try:
            root.createcommand("tk::mac::Quit", lambda: root.event_generate("<<Quit>>"))
        except tk.TclError:
            pass
    CompanionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
