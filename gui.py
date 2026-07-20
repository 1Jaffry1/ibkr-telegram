"""
IBKR Trade Alerts — companion window + settings.

Run this file to open the always-on companion:
  Start/Stop monitoring, shortcut Telegram buttons, and Settings.
"""

import os
import platform
import threading
import tkinter as tk
from tkinter import ttk

from client import MonitorController, send_telegram_message, reload_env
from config_store import (
    load_config,
    save_config,
    read_env_values,
    save_env_and_secrets,
    shortcut_increments_counter,
    summary_role_for_shortcut,
)
from summary_store import (
    DEFAULT_LONG_TERM_SUMMARY_MESSAGE,
    DEFAULT_SUMMARY_MESSAGE,
    apply_cnt_placeholder,
    counter_label_text,
    format_summary_message,
    format_summary_preview,
    increment_trade_counter,
    record_indicator,
    reset_summary,
    reset_trade_counter,
    summary_label_text,
)
from telegram_room import TitleChangeCleaner, room_settings, set_room_state


# --- Colors / theme ---------------------------------------------------------

LIGHT_COLORS = {
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
    "header_sub": "#DDF4FF",
    "secondary_btn": "#EAEEF2",
    "log_bg": "#0D1117",
    "log_fg": "#E6EDF3",
    "log_ok": "#3FB950",
    "log_err": "#FF7B72",
    "log_info": "#58A6FF",
}

DARK_COLORS = {
    "bg": "#0D1117",
    "surface": "#161B22",
    "primary": "#388BFD",
    "primary_dark": "#1F6FEB",
    "success": "#3FB950",
    "danger": "#F85149",
    "warning": "#D29922",
    "text": "#E6EDF3",
    "muted": "#8B949E",
    "border": "#30363D",
    "accent": "#1F2937",
    "header_sub": "#A5D6FF",
    "secondary_btn": "#21262D",
    "log_bg": "#010409",
    "log_fg": "#E6EDF3",
    "log_ok": "#3FB950",
    "log_err": "#FF7B72",
    "log_info": "#58A6FF",
}

# Active palette (mutated by set_color_theme)
COLORS = dict(LIGHT_COLORS)
_DARK_MODE = False


def set_color_theme(dark=False):
    """Switch the active COLORS palette."""
    global _DARK_MODE
    _DARK_MODE = bool(dark)
    COLORS.clear()
    COLORS.update(DARK_COLORS if _DARK_MODE else LIGHT_COLORS)
    return _DARK_MODE


def is_dark_mode():
    return _DARK_MODE

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
   • Room controls: OPEN/CLOSE ROOM renames the Telegram channel
     (bot must be channel admin with Change Info + Delete Messages)

6) RUN
   Companion window → Start Monitoring
   Keep IB Gateway/TWS open while monitoring.

Tips
---
• Paper vs live is only the port + which IBKR session you login to
• If no alerts appear: confirm Client ID 0 + Master API Client ID 0
• Activity log on the companion shows connection and trade events
• Cmd/Ctrl+Z undoes text edits; Cmd/Ctrl+Shift+Z (or Ctrl+Y) redoes
• Dark mode toggle is in the companion header; window size is remembered
• Widen the companion window to lay shortcut / summary buttons out in a grid
• Trackpad / mouse-wheel scrolls Settings tabs and the companion body
• Telegram posts a “name changed” notice on rename (bots cannot mute that);
  this app deletes the notice as soon as it appears
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
  {cnt}                  Trade ID as number emoji (e.g. 1️⃣4️⃣ for 14)

Trade ID ({cnt}):
  Optional — omit {cnt} from any template that should not show an ID.
  The counter is incremented when you press a shortcut marked
  “Increment trade ID” on the Shortcuts tab (multiple allowed).
  Example: put {cnt} on “Starting trade” and on fill templates
  so alerts for that trade share the same ID.

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

Summary templates (Summary / Long-term Summary buttons):
  {trades}               Trades taken count
  {green}                Green count
  {red}                  Red count
  {cnt}                  Current trade ID emoji (optional)
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

def apply_theme(root, dark=None):
    """Use a colored clam theme (light or dark)."""
    if dark is not None:
        set_color_theme(dark)

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
    style.map(
        "TButton",
        background=[("active", COLORS["primary_dark"]), ("disabled", COLORS["border"])],
        foreground=[("disabled", COLORS["muted"])],
    )
    style.configure("Success.TButton", background=COLORS["success"], foreground="#FFFFFF")
    style.map("Success.TButton", background=[("active", COLORS["success"]), ("disabled", COLORS["border"])])
    style.configure("Danger.TButton", background=COLORS["danger"], foreground="#FFFFFF")
    style.map("Danger.TButton", background=[("active", COLORS["danger"]), ("disabled", COLORS["border"])])
    style.configure("Secondary.TButton", background=COLORS["secondary_btn"], foreground=COLORS["text"])
    style.map("Secondary.TButton", background=[("active", COLORS["border"])])
    style.configure("TEntry", fieldbackground=COLORS["surface"], foreground=COLORS["text"], insertcolor=COLORS["text"])
    style.map("TEntry", fieldbackground=[("readonly", COLORS["surface"])], foreground=[("readonly", COLORS["text"])])
    style.configure("TCheckbutton", background=COLORS["bg"], foreground=COLORS["text"])
    style.map("TCheckbutton", background=[("active", COLORS["bg"])])
    style.configure("TCombobox", fieldbackground=COLORS["surface"], foreground=COLORS["text"], background=COLORS["surface"])
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["surface"])], foreground=[("readonly", COLORS["text"])])
    style.configure("TSeparator", background=COLORS["border"])
    style.configure("Vertical.TScrollbar", background=COLORS["border"], troughcolor=COLORS["bg"])
    style.configure("Horizontal.TScrollbar", background=COLORS["border"], troughcolor=COLORS["bg"])


def bind_mousewheel(scroll_target, *hover_roots):
    """Enable touchpad / mouse-wheel scrolling over a Canvas or Text widget."""

    def _delta_units(event):
        delta = getattr(event, "delta", 0) or 0
        if delta:
            if platform.system() == "Darwin":
                return -int(delta)
            # Windows / most X11: multiples of 120
            if abs(delta) >= 120:
                return -int(delta / 120)
            return -1 if delta > 0 else 1
        num = getattr(event, "num", None)
        if num == 4:
            return -1
        if num == 5:
            return 1
        return 0

    def on_wheel(event):
        units = _delta_units(event)
        if not units:
            return
        try:
            scroll_target.yview_scroll(units, "units")
        except tk.TclError:
            return
        return "break"

    def attach(widget):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(seq, on_wheel, add="+")
        for child in widget.winfo_children():
            attach(child)

    roots = hover_roots or (scroll_target,)
    for root_widget in roots:
        attach(root_widget)
        # Re-attach when new children appear (settings forms grow dynamically)
        root_widget.bind(
            "<Map>",
            lambda e, w=root_widget: attach(w),
            add="+",
        )


def grid_columns_for_width(width, min_col_width=180, max_cols=4):
    """How many button columns fit in a wide companion window."""
    try:
        width = int(width)
    except (TypeError, ValueError):
        width = 0
    if width < 520:
        return 1
    cols = max(1, width // min_col_width)
    return max(1, min(max_cols, cols))


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


def ask_send_preview(parent, title, message):
    """Preview dialog with Send / Cancel. Returns True if user chooses Send."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.configure(bg=COLORS["surface"])
    result = {"value": False}

    body = tk.Frame(dialog, bg=COLORS["surface"], padx=20, pady=18)
    body.pack(fill="both", expand=True)
    tk.Label(
        body,
        text=title,
        bg=COLORS["surface"],
        fg=COLORS["text"],
        font=("Segoe UI", 13, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        body,
        text=message,
        bg=COLORS["surface"],
        fg=COLORS["text"],
        justify="left",
        wraplength=380,
        anchor="w",
    ).pack(fill="x", pady=(10, 0))

    buttons = tk.Frame(body, bg=COLORS["surface"])
    buttons.pack(fill="x", pady=(16, 0))

    def close(value=False):
        result["value"] = value
        dialog.destroy()

    ttk.Button(buttons, text="Cancel", style="Secondary.TButton", command=lambda: close(False)).pack(
        side="right", padx=(8, 0)
    )
    ttk.Button(buttons, text="Send", style="Success.TButton", command=lambda: close(True)).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
    center_on_parent(dialog, parent, width=440, height=260)
    parent.wait_window(dialog)
    return result["value"]


_UNDO_SEQS = (
    "<Control-z>",
    "<Control-Z>",
    "<Command-z>",
    "<Command-Z>",
    "<Meta-z>",
    "<Meta-Z>",
)
_REDO_SEQS = (
    "<Control-y>",
    "<Control-Y>",
    "<Control-Shift-Z>",
    "<Control-Shift-z>",
    "<Command-Shift-Z>",
    "<Command-Shift-z>",
    "<Command-y>",
    "<Command-Y>",
    "<Meta-y>",
    "<Meta-Y>",
    "<Meta-Shift-Z>",
    "<Meta-Shift-z>",
)


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

    for seq in _UNDO_SEQS:
        widget.bind(seq, undo_event)
    for seq in _REDO_SEQS:
        widget.bind(seq, redo_event)


def enable_entry_undo(entry):
    """Simple undo/redo stack for ttk/tk Entry widgets (Cmd/Ctrl+Z)."""
    history = [entry.get()]
    index = {"i": 0}
    applying = {"flag": False}

    def snapshot(event=None):
        if applying["flag"]:
            return
        try:
            value = entry.get()
        except tk.TclError:
            return
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
        try:
            entry.delete(0, "end")
            entry.insert(0, history[index["i"]])
        finally:
            applying["flag"] = False
        return "break"

    def redo(event=None):
        if index["i"] >= len(history) - 1:
            return "break"
        index["i"] += 1
        applying["flag"] = True
        try:
            entry.delete(0, "end")
            entry.insert(0, history[index["i"]])
        finally:
            applying["flag"] = False
        return "break"

    entry.bind("<KeyRelease>", snapshot, add="+")
    entry.bind("<<Paste>>", lambda e: entry.after_idle(snapshot), add="+")
    entry.bind("<FocusOut>", snapshot, add="+")
    for seq in _UNDO_SEQS:
        entry.bind(seq, undo)
    for seq in _REDO_SEQS:
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
        apply_theme(self, dark=is_dark_mode())
        self.configure(bg=COLORS["bg"])
        self.transient(master)
        self.on_saved = on_saved
        self.app_config = load_config()
        self.load_env_file()
        self.exception_rows = []
        self.shortcut_rows = []
        self._scroll_canvases = []

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
        self.create_room_tab()
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
        canvas = tk.Canvas(outer, highlightthickness=0, bg=COLORS["bg"], bd=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas, padding="16")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        bind_mousewheel(canvas, canvas, frame, outer)
        if not hasattr(self, "_scroll_canvases"):
            self._scroll_canvases = []
        self._scroll_canvases.append(canvas)
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

    def create_room_tab(self):
        frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(frame, text="Room")
        room = room_settings(self.app_config)

        ttk.Label(frame, text="Channel Room Controls", style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(
            frame,
            text=(
                "OPEN ROOM / CLOSE ROOM rename your Telegram channel to:\n"
                "  {current name} - ROOM OPEN\n"
                "  {current name} - ROOM CLOSED\n\n"
                "The base name is kept; only the status suffix changes.\n\n"
                "Telegram does not allow bots to mute channel notifications before a rename "
                "(no silent mode for title changes). This app instead deletes the automatic "
                "“name changed” notice as quickly as possible.\n\n"
                "Bot must be channel admin with: Change Channel Info + Delete Messages."
            ),
            style="Muted.TLabel",
            justify="left",
            wraplength=620,
        ).pack(anchor="w", pady=(0, 14))

        form = ttk.Frame(frame)
        form.pack(anchor="w", fill="x")

        self.room_open_button = tk.StringVar(value=room["open_button"])
        self.room_close_button = tk.StringVar(value=room["close_button"])
        self.room_open_text = tk.StringVar(value=room["open_text"])
        self.room_closed_text = tk.StringVar(value=room["closed_text"])

        rows = [
            ("Open button label", self.room_open_button),
            ("Close button label", self.room_close_button),
            ("Open status text (in channel name)", self.room_open_text),
            ("Closed status text (in channel name)", self.room_closed_text),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(form, text=label + ":").grid(row=i, column=0, sticky="w", pady=6)
            make_entry(form, textvariable=var, width=40).grid(row=i, column=1, sticky="w", padx=10, pady=6)

        ttk.Label(
            frame,
            text='Example: base "My Desk" + open text "ROOM OPEN" → "My Desk - ROOM OPEN"',
            style="Muted.TLabel",
            wraplength=620,
        ).pack(anchor="w", pady=(16, 0))

    def create_shortcuts_tab(self):
        frame = self._create_scrollable_tab("Shortcuts")
        ttk.Label(frame, text="Companion Shortcut Buttons", style="Heading.TLabel").pack(anchor="w", pady=8)
        ttk.Label(frame, text="These appear on the companion window and send a Telegram message when clicked.", style="Muted.TLabel", wraplength=640).pack(anchor="w", pady=(0, 10))

        self.shortcuts_frame = ttk.Frame(frame)
        self.shortcuts_frame.pack(fill="x")
        ttk.Button(frame, text="➕ Add Shortcut", style="Secondary.TButton", command=self._add_shortcut_row).pack(anchor="w", pady=8)

        role_by_id = {}
        for role, ids in (self.app_config.get("summary_indicators") or {}).items():
            for sid in ids or []:
                role_by_id[str(sid)] = role
        counter_ids = {str(sid) for sid in (self.app_config.get("trade_counter_shortcuts") or [])}

        for item in self.app_config.get("shortcuts", []):
            item = dict(item)
            sid = str(item.get("id") or "")
            item["summary_role"] = role_by_id.get(sid, "none")
            item["increment_counter"] = sid in counter_ids
            self._add_shortcut_row(item)
        if not self.shortcut_rows:
            self._add_shortcut_row()

        ttk.Label(frame, text="Summary Indicators", style="Heading.TLabel").pack(anchor="w", pady=(16, 4))
        ttk.Label(
            frame,
            text=(
                "For each shortcut, choose whether it counts toward the summary when pressed: "
                "Green trade, Red trade, or Close trade (trades taken only). "
                "You can assign multiple shortcuts to the same role. Leave as None for normal shortcuts."
            ),
            style="Muted.TLabel",
            wraplength=640,
        ).pack(anchor="w", pady=(0, 4))
        ttk.Label(
            frame,
            text=(
                "Trade ID: check “Increment trade ID” on one or more shortcuts (e.g. Starting Trade). "
                "Use {cnt} in message templates / shortcut text for the number-emoji ID (1️⃣4️⃣)."
            ),
            style="Muted.TLabel",
            wraplength=640,
        ).pack(anchor="w", pady=(0, 8))

    def _add_shortcut_row(self, data=None):
        data = data or {
            "id": "",
            "label": "",
            "message": "",
            "summary_role": "none",
            "increment_counter": False,
        }
        row_frame = ttk.LabelFrame(self.shortcuts_frame, text="Shortcut", padding=8)
        row_frame.pack(fill="x", pady=6)

        label_var = tk.StringVar(value=data.get("label", ""))
        id_value = data.get("id") or ""
        role_labels = {
            "none": "None",
            "green": "Green trade",
            "red": "Red trade",
            "close": "Close trade",
        }
        label_to_role = {v: k for k, v in role_labels.items()}
        role_value = str(data.get("summary_role") or "none").lower()
        if role_value not in role_labels:
            role_value = "none"
        role_var = tk.StringVar(value=role_labels[role_value])
        increment_var = tk.BooleanVar(value=bool(data.get("increment_counter")))

        ttk.Label(row_frame, text="Button label:").grid(row=0, column=0, sticky="w")
        make_entry(row_frame, textvariable=label_var, width=28).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(row_frame, text="Telegram message:").grid(row=1, column=0, sticky="nw", pady=4)
        msg_box = make_text(row_frame, height=3, width=55, wrap="word")
        msg_box.insert("1.0", data.get("message", ""))
        msg_box.grid(row=1, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(row_frame, text="Summary indicator:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        role_box = ttk.Combobox(
            row_frame,
            textvariable=role_var,
            values=tuple(role_labels.values()),
            state="readonly",
            width=16,
        )
        role_box.grid(row=2, column=1, sticky="w", padx=6, pady=(4, 0))
        ttk.Checkbutton(
            row_frame,
            text="Increment trade ID",
            variable=increment_var,
        ).grid(row=3, column=1, sticky="w", padx=6, pady=(6, 0))

        row_data = {
            "frame": row_frame,
            "id": id_value,
            "label": label_var,
            "message_box": msg_box,
            "summary_role": role_var,
            "summary_role_map": label_to_role,
            "increment_counter": increment_var,
        }

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
            ("Summary", "summary_message", "SUMMARY_MESSAGE", DEFAULT_SUMMARY_MESSAGE, 6),
            ("Long-term Summary", "long_term_summary_message", "LONG_TERM_SUMMARY_MESSAGE", DEFAULT_LONG_TERM_SUMMARY_MESSAGE, 6),
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
        if not self.summary_message.get("1.0", "end-1c").strip() or not self.long_term_summary_message.get("1.0", "end-1c").strip():
            show_error(self, "Error", "Summary and Long-term Summary templates cannot be empty.")
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
        summary_indicators = {"green": [], "red": [], "close": []}
        trade_counter_shortcuts = []
        for row in self.shortcut_rows:
            label = row["label"].get().strip()
            message = row["message_box"].get("1.0", "end-1c").strip()
            if not label and not message:
                continue
            if not label or not message:
                show_error(self, "Error", "Each shortcut needs both a label and a message.")
                return
            shortcut_id = row["id"] or label.lower().replace(" ", "_")
            shortcuts.append({
                "id": shortcut_id,
                "label": label,
                "message": message,
            })
            role_label = row["summary_role"].get() if row.get("summary_role") else "None"
            role = (row.get("summary_role_map") or {}).get(role_label, "none")
            if role in summary_indicators:
                summary_indicators[role].append(shortcut_id)
            if row.get("increment_counter") and row["increment_counter"].get():
                trade_counter_shortcuts.append(shortcut_id)
        if not shortcuts:
            show_error(self, "Error", "Add at least one shortcut, or keep the defaults.")
            return

        room_open_text = self.room_open_text.get().strip()
        room_closed_text = self.room_closed_text.get().strip()
        if not room_open_text or not room_closed_text:
            show_error(self, "Error", "Room open/closed status text cannot be empty.")
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
            'SUMMARY_MESSAGE': self.summary_message.get("1.0", "end-1c"),
            'LONG_TERM_SUMMARY_MESSAGE': self.long_term_summary_message.get("1.0", "end-1c"),
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
            "dark_mode": existing.get("dark_mode", False),
            "window_geometry": existing.get("window_geometry", ""),
            "room": {
                "open_button": self.room_open_button.get().strip() or "OPEN ROOM",
                "close_button": self.room_close_button.get().strip() or "CLOSE ROOM",
                "open_text": room_open_text,
                "closed_text": room_closed_text,
            },
            "shortcuts": shortcuts,
            "summary_indicators": summary_indicators,
            "trade_counter_shortcuts": trade_counter_shortcuts,
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
        self.root.minsize(420, 520)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root._companion_app = self

        self.controller = MonitorController(status_callback=self._queue_status)
        self._status_queue = []
        self.settings_window = None
        self.help_window = None
        self.app_config = load_config()
        self.title_cleaner = TitleChangeCleaner(status_callback=self._queue_status)
        self._shortcut_buttons = []
        self._summary_buttons = []
        self._layout_after = None
        self._geometry_after = None
        self._last_shortcut_cols = None
        self._last_summary_wide = None

        apply_theme(root, dark=bool(self.app_config.get("dark_mode")))
        saved_geom = str(self.app_config.get("window_geometry") or "").strip()
        self.root.geometry(saved_geom if saved_geom else "520x760")

        self.header = tk.Frame(root, bg=COLORS["primary"], padx=16, pady=14)
        self.header.pack(fill="x")
        header_top = tk.Frame(self.header, bg=COLORS["primary"])
        header_top.pack(fill="x")
        self.title_label = tk.Label(
            header_top,
            text="IBKR Trade Alerts",
            bg=COLORS["primary"],
            fg="#FFFFFF",
            font=("Segoe UI", 18, "bold"),
        )
        self.title_label.pack(side="left", anchor="w")
        self.theme_btn = ttk.Button(
            header_top,
            text=self._theme_button_label(),
            style="Secondary.TButton",
            command=self.toggle_dark_mode,
        )
        self.theme_btn.pack(side="right")
        self.status_label = tk.Label(
            self.header,
            text="Status: Idle",
            bg=COLORS["primary"],
            fg=COLORS["header_sub"],
        )
        self.status_label.pack(anchor="w", pady=(4, 0))

        # Scrollable main body (touchpad-friendly) so a wide/short window still works
        body_outer = ttk.Frame(root)
        body_outer.pack(fill="both", expand=True)
        self.body_canvas = tk.Canvas(body_outer, highlightthickness=0, bg=COLORS["bg"], bd=0)
        body_scroll = ttk.Scrollbar(body_outer, orient="vertical", command=self.body_canvas.yview)
        self.content = ttk.Frame(self.body_canvas)
        self.content.bind(
            "<Configure>",
            lambda e: self.body_canvas.configure(scrollregion=self.body_canvas.bbox("all")),
        )
        self._content_window = self.body_canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.body_canvas.configure(yscrollcommand=body_scroll.set)
        self.body_canvas.bind("<Configure>", self._on_body_canvas_configure)
        self.body_canvas.pack(side="left", fill="both", expand=True)
        body_scroll.pack(side="right", fill="y")
        bind_mousewheel(self.body_canvas, self.body_canvas, self.content, body_outer)

        controls = ttk.Frame(self.content, padding=12)
        controls.pack(fill="x")
        self.start_btn = ttk.Button(controls, text="▶ Start Monitoring", style="Success.TButton", command=self.start_monitoring)
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ttk.Button(controls, text="⏹ Stop", style="Danger.TButton", command=self.stop_monitoring, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="❓ Help", style="Secondary.TButton", command=self.open_help).pack(side="right")
        ttk.Button(controls, text="⚙ Settings", command=self.open_settings).pack(side="right", padx=(0, 8))

        room_wrap = ttk.LabelFrame(self.content, text="Room", padding=12)
        room_wrap.pack(fill="x", padx=12, pady=(8, 0))
        self.room_btns = ttk.Frame(room_wrap)
        self.room_btns.pack(fill="x")
        self.open_room_btn = ttk.Button(
            self.room_btns, text="OPEN ROOM", style="Success.TButton", command=lambda: self.set_room(True)
        )
        self.close_room_btn = ttk.Button(
            self.room_btns, text="CLOSE ROOM", style="Danger.TButton", command=lambda: self.set_room(False)
        )
        self.room_hint = ttk.Label(room_wrap, text="", style="Muted.TLabel", wraplength=440)
        self.room_hint.pack(anchor="w", pady=(8, 0))

        summary_wrap = ttk.LabelFrame(self.content, text="Summary", padding=12)
        summary_wrap.pack(fill="x", padx=12, pady=(8, 0))
        self.summary_btns = ttk.Frame(summary_wrap)
        self.summary_btns.pack(fill="x")
        self._summary_buttons = [
            ttk.Button(self.summary_btns, text="Summary", command=lambda: self.preview_and_send_summary("session")),
            ttk.Button(
                self.summary_btns,
                text="Reset Summary",
                style="Secondary.TButton",
                command=lambda: self.reset_trade_summary("session"),
            ),
            ttk.Button(
                self.summary_btns,
                text="Long-term Summary",
                command=lambda: self.preview_and_send_summary("long_term"),
            ),
            ttk.Button(
                self.summary_btns,
                text="Reset Long-term",
                style="Secondary.TButton",
                command=lambda: self.reset_trade_summary("long_term"),
            ),
        ]
        self.summary_hint = ttk.Label(summary_wrap, text="", style="Muted.TLabel", wraplength=440)
        self.summary_hint.pack(anchor="w", pady=(8, 0))
        counter_row = ttk.Frame(summary_wrap)
        counter_row.pack(fill="x", pady=(8, 0))
        self.counter_hint = ttk.Label(counter_row, text="", style="Muted.TLabel", wraplength=320)
        self.counter_hint.pack(side="left", fill="x", expand=True)
        ttk.Button(
            counter_row,
            text="Reset Trade ID",
            style="Secondary.TButton",
            command=self.reset_trade_id,
        ).pack(side="right")
        self.summary_help = ttk.Label(
            summary_wrap,
            text="Summary: Green / Red / Close shortcuts.  Trade ID: Increment trade ID shortcuts + {cnt} in templates.",
            style="Muted.TLabel",
            wraplength=440,
        )
        self.summary_help.pack(anchor="w", pady=(4, 0))
        self.refresh_summary_label()

        shortcuts_wrap = ttk.LabelFrame(self.content, text="Shortcuts", padding=12)
        shortcuts_wrap.pack(fill="x", padx=12, pady=8)
        self.shortcuts_container = ttk.Frame(shortcuts_wrap)
        self.shortcuts_container.pack(fill="x")
        self.shortcuts_hint = ttk.Label(
            shortcuts_wrap,
            text="Widen the window to arrange shortcut buttons in a grid.",
            style="Muted.TLabel",
            wraplength=440,
        )
        self.shortcuts_hint.pack(anchor="w", pady=(6, 0))

        log_wrap = ttk.LabelFrame(self.content, text="Activity", padding=8)
        log_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log = tk.Text(
            log_wrap,
            height=12,
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
        bind_mousewheel(self.log, self.log, log_wrap)

        self.refresh_shortcuts()
        self.refresh_room_controls()
        self._relayout_buttons(force=True)

        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self.root.after(200, self._drain_status_queue)
        self.append_log("Companion ready. Open Help for first-use IBKR setup, then Start Monitoring.", "info")
        self.append_log("Tip: widen the window for a button grid · toggle Dark/Light in the header · Cmd/Ctrl+Z undoes text edits.", "info")
        self.root.after(400, self._maybe_show_first_use_guide)
        self.title_cleaner.start()

    def _theme_button_label(self):
        return "Light mode" if is_dark_mode() else "Dark mode"

    def _on_body_canvas_configure(self, event):
        self.body_canvas.itemconfigure(self._content_window, width=event.width)

    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        if self._layout_after:
            self.root.after_cancel(self._layout_after)
        self._layout_after = self.root.after(80, lambda: self._relayout_buttons(force=False))
        if self._geometry_after:
            self.root.after_cancel(self._geometry_after)
        self._geometry_after = self.root.after(400, self._persist_geometry)

    def _persist_geometry(self):
        self._geometry_after = None
        try:
            geometry = self.root.winfo_geometry()
        except tk.TclError:
            return
        cfg = load_config()
        if cfg.get("window_geometry") == geometry:
            return
        cfg["window_geometry"] = geometry
        save_config(cfg)
        self.app_config = cfg

    def toggle_dark_mode(self):
        dark = not is_dark_mode()
        apply_theme(self.root, dark=dark)
        cfg = load_config()
        cfg["dark_mode"] = dark
        save_config(cfg)
        self.app_config = cfg
        self.apply_runtime_colors()
        self.theme_btn.config(text=self._theme_button_label())
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.configure(bg=COLORS["bg"])
            apply_theme(self.settings_window, dark=dark)
            for canvas in getattr(self.settings_window, "_scroll_canvases", []):
                try:
                    canvas.configure(bg=COLORS["bg"])
                except tk.TclError:
                    pass
        self.append_log("Switched to dark mode." if dark else "Switched to light mode.", "info")

    def apply_runtime_colors(self):
        """Update non-ttk widgets after a theme change."""
        self.root.configure(bg=COLORS["bg"])
        self.header.configure(bg=COLORS["primary"])
        self.title_label.configure(bg=COLORS["primary"], fg="#FFFFFF")
        self.status_label.configure(bg=COLORS["primary"], fg=COLORS["header_sub"])
        self.body_canvas.configure(bg=COLORS["bg"])
        self.log.configure(
            bg=COLORS["log_bg"],
            fg=COLORS["log_fg"],
            insertbackground=COLORS["log_fg"],
        )
        self.log.tag_configure("ok", foreground=COLORS["log_ok"])
        self.log.tag_configure("err", foreground=COLORS["log_err"])
        self.log.tag_configure("info", foreground=COLORS["log_info"])

    def _relayout_buttons(self, force=False):
        self._layout_after = None
        width = max(self.root.winfo_width(), self.content.winfo_width(), 1)
        wrap = max(280, width - 48)
        for label in (self.room_hint, self.summary_hint, self.summary_help, self.shortcuts_hint, self.counter_hint):
            try:
                label.configure(wraplength=wrap)
            except tk.TclError:
                pass

        # Room: 2 columns when wide enough, else stacked
        room_wide = width >= 560
        for btn in (self.open_room_btn, self.close_room_btn):
            try:
                btn.grid_forget()
            except tk.TclError:
                pass
            try:
                btn.pack_forget()
            except tk.TclError:
                pass
        if room_wide:
            self.room_btns.columnconfigure(0, weight=1)
            self.room_btns.columnconfigure(1, weight=1)
            self.open_room_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            self.close_room_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        else:
            self.open_room_btn.pack(fill="x", pady=(0, 6))
            self.close_room_btn.pack(fill="x")

        # Summary: 1x4 when wide, else 2x2
        summary_wide = width >= 720
        if force or summary_wide != self._last_summary_wide:
            self._last_summary_wide = summary_wide
            for btn in self._summary_buttons:
                btn.grid_forget()
            cols = 4 if summary_wide else 2
            for i in range(cols):
                self.summary_btns.columnconfigure(i, weight=1)
            for i, btn in enumerate(self._summary_buttons):
                r, c = divmod(i, cols)
                pad_x = (0, 6) if c < cols - 1 else (0, 0)
                pad_y = (0, 8) if r == 0 and cols == 2 else (0, 0)
                btn.grid(row=r, column=c, sticky="ew", padx=pad_x, pady=pad_y)

        # Shortcuts grid
        cols = grid_columns_for_width(width)
        if not self._shortcut_buttons:
            return
        if not force and cols == self._last_shortcut_cols:
            return
        self._last_shortcut_cols = cols
        for btn in self._shortcut_buttons:
            btn.grid_forget()
        for i in range(cols):
            self.shortcuts_container.columnconfigure(i, weight=1)
        for i, btn in enumerate(self._shortcut_buttons):
            r, c = divmod(i, cols)
            btn.grid(row=r, column=c, sticky="ew", padx=4, pady=4)

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

    def refresh_room_controls(self):
        self.app_config = load_config()
        room = room_settings(self.app_config)
        self.open_room_btn.config(text=room["open_button"])
        self.close_room_btn.config(text=room["close_button"])
        self.room_hint.config(
            text=f'Names become:  … - {room["open_text"]}   /   … - {room["closed_text"]}'
        )

    def refresh_shortcuts(self):
        for child in self.shortcuts_container.winfo_children():
            child.destroy()
        self._shortcut_buttons = []
        self._last_shortcut_cols = None
        self.app_config = load_config()
        self.refresh_room_controls()
        shortcuts = self.app_config.get("shortcuts") or []
        if not shortcuts:
            ttk.Label(self.shortcuts_container, text="No shortcuts configured.", style="Muted.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            return
        for item in shortcuts:
            btn = ttk.Button(
                self.shortcuts_container,
                text=item.get("label", "Shortcut"),
                command=lambda shortcut=item: self.send_shortcut(shortcut),
            )
            self._shortcut_buttons.append(btn)
        self._relayout_buttons(force=True)

    def set_room(self, is_open):
        reload_env()
        self.open_room_btn.config(state="disabled")
        self.close_room_btn.config(state="disabled")
        self.append_log("Updating channel room status...", "info")

        def work():
            ok, title, detail = set_room_state(is_open)
            self.root.after(0, lambda: self._room_done(ok, title, detail))

        threading.Thread(target=work, daemon=True).start()

    def _room_done(self, ok, title, detail):
        self.open_room_btn.config(state="normal")
        self.close_room_btn.config(state="normal")
        if ok:
            self.append_log(detail, "ok")
            if title:
                self.append_log(f"Channel title: {title}", "info")
        else:
            self.append_log(detail, "err")
            show_error(self.root, "Room update failed", detail)

    def send_shortcut(self, shortcut):
        if isinstance(shortcut, str):
            shortcut = {"message": shortcut, "id": "", "label": "Shortcut"}
        message = shortcut.get("message", "")
        reload_env()
        if not os.getenv('TELEGRAM_BOT_TOKEN') or not os.getenv('TELEGRAM_CHAT_ID'):
            show_error(self.root, "Error", "Set Telegram credentials in Settings first.")
            return

        self.app_config = load_config()
        cnt_emoji = None
        if shortcut_increments_counter(shortcut.get("id"), self.app_config):
            value, cnt_emoji = increment_trade_counter()
            self.refresh_summary_label()
            self.append_log(f"Trade ID → {value}  {cnt_emoji}", "info")
        message = apply_cnt_placeholder(message, cnt_emoji)

        message_id = send_telegram_message(message)
        if message_id:
            preview = message.splitlines()[0] if message else shortcut.get("label", "Shortcut")
            self.append_log(f"Shortcut sent: {preview}", "ok")
            role = summary_role_for_shortcut(shortcut.get("id"), self.app_config)
            if role:
                record_indicator(role)
                self.refresh_summary_label()
                self.append_log(f"Summary counted as {role} trade.", "info")
        else:
            self.append_log("Failed to send shortcut message.", "err")
            show_error(self.root, "Error", "Failed to send Telegram message.")

    def refresh_summary_label(self):
        self.summary_hint.config(text=summary_label_text())
        if hasattr(self, "counter_hint"):
            self.counter_hint.config(text=counter_label_text())

    def reset_trade_id(self):
        if not ask_yes_no(self.root, "Reset", "Reset trade ID counter to zero?"):
            return
        reset_trade_counter()
        self.refresh_summary_label()
        self.append_log("Reset trade ID.", "info")

    def preview_and_send_summary(self, kind="session"):
        title = "Long-term Summary" if kind == "long_term" else "Summary"
        preview = format_summary_preview(kind)
        if not ask_send_preview(self.root, title, preview):
            return
        reload_env()
        if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
            show_error(self.root, "Error", "Set Telegram credentials in Settings first.")
            return
        message = format_summary_message(kind)
        message_id = send_telegram_message(message)
        if message_id:
            self.append_log(f"{title} sent to Telegram.", "ok")
        else:
            self.append_log(f"Failed to send {title.lower()}.", "err")
            show_error(self.root, "Error", "Failed to send Telegram message.")

    def reset_trade_summary(self, kind="session"):
        label = "long-term summary" if kind == "long_term" else "summary"
        if not ask_yes_no(self.root, "Reset", f"Reset {label} counters to zero?"):
            return
        reset_summary(kind)
        self.refresh_summary_label()
        self.append_log(f"Reset {label}.", "info")

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
        self._persist_geometry()
        self.title_cleaner.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    if platform.system() == "Darwin":
        try:
            root.createcommand("tk::mac::Quit", lambda: root.event_generate("<<Quit>>"))
        except tk.TclError:
            pass
    # Apply saved theme before building widgets
    cfg = load_config()
    apply_theme(root, dark=bool(cfg.get("dark_mode")))
    CompanionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
