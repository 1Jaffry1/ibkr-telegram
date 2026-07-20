"""
IBKR Trade Alerts — companion window + settings.

Run this file to open the always-on companion:
  Start/Stop monitoring, shortcut Telegram buttons, and Settings.

Built with CustomTkinter. Scroll areas use the standard Tk canvas pattern
(canvas + scrollbar + create_window inner frame + MouseWheel on the parent window).
"""

import os
import platform
import sys
import threading
import tkinter as tk

import customtkinter as ctk

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
    apply_textbox_placeholder,
    message_uses_textbox,
    shortcuts_use_textbox,
    TEXTBOX_MAX_LEN,
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


# --- Colors (CTk light/dark tuples) -----------------------------------------

APP_BG = ("#F5F6F8", "#0B1220")
CARD_FG = ("#F3F4F6", "#1F2937")
CARD_ALT_FG = ("#FFFFFF", "#111827")

HEADER_FG = ("#1E3A8A", "#0F172A")
HEADER_SUB_FG = ("#DBEAFE", "#93C5FD")
HEADER_BTN_FG = ("#2E4E9E", "#1E293B")
HEADER_BTN_HOVER = ("#3A5DB8", "#334155")

CHIP_FG = ("#FFFFFF", "#1E293B")
CHIP_TEXT_FG = ("#1E3A8A", "#DBEAFE")

TEXT_FG = ("#111827", "#F9FAFB")
HINT_FG = ("#6B7280", "#9CA3AF")

PRIMARY_FG = ("#2563EB", "#3B82F6")
PRIMARY_HOVER = ("#1D4ED8", "#2563EB")

SUCCESS_FG = ("#059669", "#10B981")
SUCCESS_HOVER = ("#047857", "#0D9668")

DANGER_FG = ("#DC2626", "#F87171")
DANGER_HOVER = ("#B91C1C", "#EF4444")

WARNING_FG = ("#D97706", "#FBBF24")

SECONDARY_FG = ("#E5E7EB", "#374151")
SECONDARY_HOVER = ("#D1D5DB", "#4B5563")
SECONDARY_TEXT_FG = ("#111827", "#F9FAFB")

BORDER_FG = ("#E5E7EB", "#1F2937")

LOG_BG = ("#0B1220", "#020617")
LOG_FG = "#E5E7EB"
LOG_OK = "#34D399"
LOG_ERR = "#F87171"
LOG_INFO = "#60A5FA"

STATUS_DOT_COLORS = {
    "idle": HINT_FG,
    "run": SUCCESS_FG,
    "warn": WARNING_FG,
    "err": DANGER_FG,
}

# Standard action icons (unicode — works on Mac/Windows without icon packs)
ICONS = {
    "app": "📡",
    "start": "▶",
    "stop": "⏹",
    "settings": "⚙",
    "help": "❓",
    "dark": "🌙",
    "light": "☀️",
    "room": "🚪",
    "open": "🟢",
    "close": "🔴",
    "summary": "📊",
    "long_term": "📈",
    "reset": "↺",
    "shortcuts": "⚡",
    "activity": "📋",
    "save": "💾",
    "test": "📤",
    "id": "🔢",
    "send": "➤",
    "cancel": "✕",
    "ok": "✓",
    "add": "➕",
    "remove": "✕",
}


# Active UI font size (points). Updated from Settings → Appearance.
_UI_FONT_SIZE = 13


def get_ui_font_size():
    return _UI_FONT_SIZE


def set_ui_font_size(size):
    global _UI_FONT_SIZE
    try:
        _UI_FONT_SIZE = max(10, min(22, int(size)))
    except (TypeError, ValueError):
        _UI_FONT_SIZE = 13
    return _UI_FONT_SIZE


def ui_font(size=None, weight="normal"):
    """Cross-platform UI font scaled by the user's Appearance setting."""
    family = "Segoe UI" if platform.system() == "Windows" else "Helvetica Neue"
    base = get_ui_font_size()
    if size is None:
        size = base
    else:
        # Treat explicit sizes as offsets from the default 13pt baseline
        size = max(9, int(size + (base - 13)))
    if weight == "bold":
        return (family, size, "bold")
    return (family, size)


def apply_appearance(dark):
    """Switch CustomTkinter's global appearance mode. Every CTk widget re-colors live."""
    ctk.set_appearance_mode("Dark" if dark else "Light")
    return bool(dark)


def is_dark_mode():
    return ctk.get_appearance_mode() == "Dark"


# Standard Tk canvas scroll host (canvas + scrollbar + create_window inner frame).
_SCROLL_WINDOWS = set()


def _scroll_blocks_wheel(widget):
    current = widget
    try:
        while current is not None:
            if isinstance(current, (ctk.CTkTextbox, ctk.CTkScrollbar, ctk.CTkSlider)):
                return True
            current = getattr(current, "master", None)
    except tk.TclError:
        return True
    return False


def _point_in_widget(widget, x_root, y_root):
    try:
        x0 = widget.winfo_rootx()
        y0 = widget.winfo_rooty()
        w, h = widget.winfo_width(), widget.winfo_height()
        return w > 1 and h > 1 and x0 <= x_root < x0 + w and y0 <= y_root < y0 + h
    except tk.TclError:
        return False


def _event_root_xy(event):
    x_root = getattr(event, "x_root", None)
    y_root = getattr(event, "y_root", None)
    if x_root is not None and y_root is not None:
        return x_root, y_root
    try:
        return event.widget.winfo_pointerxy()
    except tk.TclError:
        return None, None


def _window_wheel(event):
    try:
        window = event.widget.winfo_toplevel()
    except tk.TclError:
        return
    for panel in reversed(getattr(window, "_ibkr_scroll_panels", ())):
        if panel._wheel_blocked(event):
            continue
        if not panel._wheel_applies(event):
            continue
        if panel.on_mousewheel(event):
            return "break"


def _window_touchpad(event):
    try:
        window = event.widget.winfo_toplevel()
    except tk.TclError:
        return
    for panel in reversed(getattr(window, "_ibkr_scroll_panels", ())):
        if panel._wheel_blocked(event):
            continue
        if not panel._wheel_applies(event):
            continue
        if panel.on_touchpad(event):
            return "break"


def _ensure_window_wheel(window):
    if id(window) in _SCROLL_WINDOWS:
        return
    _SCROLL_WINDOWS.add(id(window))
    if sys.platform == "linux":
        for sequence in ("<Button-4>", "<Button-5>"):
            window.bind(sequence, _window_wheel, add="+")
            window.bind_all(sequence, _window_wheel, add="+")
    else:
        window.bind("<MouseWheel>", _window_wheel, add="+")
        window.bind_all("<MouseWheel>", _window_wheel, add="+")
        window.bind("<TouchpadScroll>", _window_touchpad, add="+")
        window.bind_all("<TouchpadScroll>", _window_touchpad, add="+")


class ScrollPanel:
    """
    Scrollable region using the standard Tk pattern:
      Canvas + Scrollbar(command=canvas.yview) + inner Frame via create_window().
    """

    def __init__(self, parent, *, window=None, full_window_wheel=False, block_widgets=None):
        self.window = window
        self.full_window_wheel = full_window_wheel
        self.block_widgets = list(block_widgets or [])

        self.host = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        self.canvas = tk.Canvas(self.host, highlightthickness=0, bd=0)
        self.scrollbar = ctk.CTkScrollbar(self.host, orientation="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.body = ctk.CTkFrame(self.canvas, fg_color="transparent", corner_radius=0)
        self._canvas_window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>", self._on_body_configure, add="+")
        self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")
        self._sync_colors()
        self._register_panel()

        self.body.after_idle(self.refresh)
        self.body.after(50, self.refresh)
        self.body.after(250, self.refresh)

    def pack(self, **kwargs):
        self.host.pack(**kwargs)

    def set_block_widgets(self, widgets):
        self.block_widgets = list(widgets)

    def _sync_colors(self):
        try:
            self.canvas.configure(bg=resolve_color(APP_BG))
        except tk.TclError:
            pass

    def _on_body_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self._canvas_window, width=event.width)

    def refresh(self):
        try:
            self.body.update_idletasks()
            bbox = self.canvas.bbox("all")
            if bbox is not None:
                self.canvas.configure(scrollregion=bbox)
        except tk.TclError:
            pass

    def _register_panel(self):
        if self.window is None:
            return
        panels = getattr(self.window, "_ibkr_scroll_panels", None)
        if panels is None:
            self.window._ibkr_scroll_panels = []
            panels = self.window._ibkr_scroll_panels
            _ensure_window_wheel(self.window)
        if self not in panels:
            panels.append(self)

    def _wheel_blocked(self, event):
        if _scroll_blocks_wheel(event.widget):
            return True
        x_root, y_root = _event_root_xy(event)
        if x_root is None:
            return True
        return any(_point_in_widget(widget, x_root, y_root) for widget in self.block_widgets)

    def _wheel_applies(self, event):
        x_root, y_root = _event_root_xy(event)
        if x_root is None:
            return False
        if self.full_window_wheel and self.window and _point_in_widget(self.window, x_root, y_root):
            return True
        return _point_in_widget(self.canvas, x_root, y_root) or _point_in_widget(self.host, x_root, y_root)

    def on_mousewheel(self, event):
        self.refresh()
        try:
            top, bottom = self.canvas.yview()
            if (bottom - top) >= 0.999:
                return False
        except tk.TclError:
            return False
        if sys.platform == "darwin":
            self.canvas.yview("scroll", -event.delta, "units")
        elif sys.platform.startswith("win"):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        else:
            self.canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        return True

    def on_touchpad(self, event):
        """Tk 9 macOS: two-finger trackpad uses <TouchpadScroll>, not <MouseWheel>."""
        self.refresh()
        try:
            top, bottom = self.canvas.yview()
            if (bottom - top) >= 0.999:
                return False
        except tk.TclError:
            return False
        try:
            dx, dy = event.widget.tk.call("tk::PreciseScrollDeltas", event.delta)
            dx, dy = int(dx), int(dy)
        except tk.TclError:
            return False
        if dy:
            self.canvas.yview("scroll", -dy, "units")
        if dx:
            left, right = self.canvas.xview()
            if (right - left) < 0.999:
                self.canvas.xview("scroll", -dx, "units")
        return bool(dx or dy)


def resolve_color(color):
    """Resolve a CTk (light, dark) tuple to the hex value for the current mode."""
    if isinstance(color, (tuple, list)):
        return color[1] if is_dark_mode() else color[0]
    return color


def icon_label(icon_key, text):
    icon = ICONS.get(icon_key, "")
    return f"{icon}  {text}".strip() if icon else text


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
  {textbox}              Shortcut-only: shared 10-char field (Shortcuts corner) fills every {textbox}

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


# --- Layout / widget helpers -------------------------------------------------

def section_card(parent, title):
    """A soft rounded card with a title label. Returns (outer_card, inner_content_frame)."""
    outer = ctk.CTkFrame(parent, corner_radius=16, border_width=0, fg_color=CARD_FG)
    ctk.CTkLabel(
        outer,
        text=title,
        font=ui_font(13, "bold"),
        text_color=TEXT_FG,
        anchor="w",
    ).pack(fill="x", padx=16, pady=(14, 6))
    inner = ctk.CTkFrame(outer, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=16, pady=(0, 14))
    return outer, inner


def make_wrap_label(parent, text="", text_color=HINT_FG, font=None, pad=24):
    """Muted/body label that reflows with parent width (avoids clipped text)."""
    label = ctk.CTkLabel(
        parent,
        text=text,
        text_color=text_color,
        font=font or ui_font(10),
        justify="left",
        anchor="w",
    )
    label._wrap_pad = pad

    def _reflow(event=None):
        try:
            width = parent.winfo_width()
            if width <= 1:
                width = parent.winfo_reqwidth()
            wrap = max(140, width - int(getattr(label, "_wrap_pad", pad)))
            label.configure(wraplength=wrap)
        except tk.TclError:
            pass

    parent.bind("<Configure>", lambda e: _reflow(), add="+")
    label.bind("<Configure>", lambda e: _reflow(), add="+")
    label.after_idle(_reflow)
    return label


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


class ToolTip:
    """Simple hover tooltip for icon-only CTk controls."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw,
            text=self.text,
            background=resolve_color(CARD_ALT_FG),
            foreground=resolve_color(TEXT_FG),
            relief="solid",
            borderwidth=1,
            font=ui_font(10),
            padx=8,
            pady=4,
        ).pack()

    def _hide(self, _event=None):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


# --- Undo/redo (Cmd/Ctrl+Z) --------------------------------------------------

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
    """Enable undo/redo for CTkTextbox (Cmd/Ctrl+Z, Cmd/Ctrl+Shift+Z, Ctrl+Y)."""
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
    """Simple undo/redo stack for CTkEntry widgets (Cmd/Ctrl+Z)."""
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


def make_textbox(parent, **kwargs):
    kwargs.setdefault("corner_radius", 10)
    kwargs.setdefault("border_width", 0)
    kwargs.setdefault("fg_color", CARD_ALT_FG)
    kwargs.setdefault("wrap", "word")
    kwargs.setdefault("font", ui_font(11))
    box = ctk.CTkTextbox(parent, **kwargs)
    enable_text_undo(box)
    return box


def make_entry(parent, **kwargs):
    kwargs.setdefault("corner_radius", 10)
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("fg_color", CARD_ALT_FG)
    entry = ctk.CTkEntry(parent, **kwargs)
    enable_entry_undo(entry)
    return entry


# --- Dialogs ------------------------------------------------------------------

def _dialog(parent, title, message, kind="info", yes_no=False):
    """Modal dialog positioned over the parent window."""
    parent = parent or tk._default_root
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.resizable(True, True)

    accent = {
        "info": PRIMARY_FG,
        "error": DANGER_FG,
        "success": SUCCESS_FG,
        "warning": WARNING_FG,
    }.get(kind, PRIMARY_FG)

    result = {"value": False}

    strip = ctk.CTkFrame(dialog, fg_color=accent, height=6, corner_radius=0)
    strip.pack(fill="x")

    body = ctk.CTkFrame(dialog, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=20, pady=18)
    ctk.CTkLabel(
        body,
        text=title,
        font=ui_font(14, "bold"),
        text_color=TEXT_FG,
        anchor="w",
    ).pack(fill="x", pady=(0, 10))

    lines = max(1, str(message).count("\n") + 1)
    box_height = min(320, max(80, lines * 20))
    msg = ctk.CTkTextbox(
        body,
        wrap="word",
        height=box_height,
        corner_radius=0,
        border_width=0,
        fg_color="transparent",
        font=ui_font(11),
    )
    msg.pack(fill="both", expand=True)
    msg.insert("1.0", str(message))
    msg.configure(state="disabled")

    buttons = ctk.CTkFrame(body, fg_color="transparent")
    buttons.pack(fill="x", pady=(16, 0))

    def close(value=False):
        result["value"] = value
        dialog.destroy()

    if yes_no:
        ctk.CTkButton(
            buttons,
            text=icon_label("cancel", "Cancel"),
            fg_color=SECONDARY_FG,
            hover_color=SECONDARY_HOVER,
            text_color=SECONDARY_TEXT_FG,
            corner_radius=12,
            command=lambda: close(False),
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            buttons,
            text=icon_label("ok", "Yes"),
            fg_color=SUCCESS_FG,
            hover_color=SUCCESS_HOVER,
            corner_radius=12,
            command=lambda: close(True),
        ).pack(side="right")
    else:
        ctk.CTkButton(
            buttons,
            text=icon_label("ok", "OK"),
            fg_color=SUCCESS_FG,
            hover_color=SUCCESS_HOVER,
            corner_radius=12,
            command=lambda: close(True),
        ).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
    height = min(560, max(240, 160 + lines * 20))
    center_on_parent(dialog, parent, width=480, height=height)
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
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.resizable(True, True)
    result = {"value": False}

    body = ctk.CTkFrame(dialog, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=20, pady=18)
    ctk.CTkLabel(
        body,
        text=icon_label("summary", title),
        font=ui_font(14, "bold"),
        text_color=TEXT_FG,
        anchor="w",
    ).pack(fill="x")
    ctk.CTkLabel(
        body,
        text="Preview — nothing is sent until you confirm.",
        font=ui_font(10),
        text_color=HINT_FG,
        anchor="w",
    ).pack(anchor="w", pady=(4, 10))

    lines = max(1, str(message).count("\n") + 1)
    box_height = min(360, max(120, lines * 20))
    card = ctk.CTkFrame(body, corner_radius=12, border_width=0, fg_color=CARD_FG)
    card.pack(fill="both", expand=True)
    msg = ctk.CTkTextbox(
        card,
        wrap="word",
        height=box_height,
        corner_radius=10,
        border_width=0,
        fg_color=CARD_ALT_FG,
        font=ui_font(11),
    )
    msg.pack(fill="both", expand=True, padx=10, pady=10)
    msg.insert("1.0", str(message))
    msg.configure(state="disabled")

    buttons = ctk.CTkFrame(body, fg_color="transparent")
    buttons.pack(fill="x", pady=(16, 0))

    def close(value=False):
        result["value"] = value
        dialog.destroy()

    ctk.CTkButton(
        buttons,
        text=icon_label("cancel", "Cancel"),
        fg_color=SECONDARY_FG,
        hover_color=SECONDARY_HOVER,
        text_color=SECONDARY_TEXT_FG,
        corner_radius=12,
        command=lambda: close(False),
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        buttons,
        text=icon_label("send", "Send"),
        fg_color=SUCCESS_FG,
        hover_color=SUCCESS_HOVER,
        corner_radius=12,
        command=lambda: close(True),
    ).pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
    height = min(600, max(320, 200 + lines * 18))
    center_on_parent(dialog, parent, width=520, height=height)
    parent.wait_window(dialog)
    return result["value"]


# --- Small button factories ---------------------------------------------------

def icon_button(parent, icon_key, command, tooltip=None, size=40):
    btn = ctk.CTkButton(
        parent,
        text=ICONS.get(icon_key, "?"),
        width=size,
        height=size,
        corner_radius=14,
        fg_color=SECONDARY_FG,
        hover_color=SECONDARY_HOVER,
        text_color=SECONDARY_TEXT_FG,
        font=ui_font(22),
        command=command,
    )
    if tooltip:
        ToolTip(btn, tooltip)
    return btn


# --- Help window ---------------------------------------------------------------

class HelpWindow(ctk.CTkToplevel):
    def __init__(self, master, on_close=None, on_open_settings=None):
        super().__init__(master)
        self.title("Setup Guide")
        self.on_close_cb = on_close
        self.on_open_settings = on_open_settings
        self.transient(master)

        header = ctk.CTkFrame(self, corner_radius=0, fg_color=HEADER_FG)
        header.pack(fill="x")
        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)
        ctk.CTkLabel(
            inner,
            text=icon_label("help", "First-Use Setup Guide"),
            text_color="#FFFFFF",
            font=ui_font(15, "bold"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            inner,
            text="IBKR API + Telegram checklist before monitoring",
            text_color=HEADER_SUB_FG,
            font=ui_font(11),
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=14)
        text = make_textbox(body, height=460, fg_color=CARD_ALT_FG, corner_radius=12, border_width=0)
        text.pack(fill="both", expand=True)
        text.insert("1.0", FIRST_USE_GUIDE)
        text.configure(state="disabled")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(
            footer,
            text=icon_label("settings", "Open Settings"),
            fg_color=SUCCESS_FG,
            hover_color=SUCCESS_HOVER,
            corner_radius=12,
            command=self._open_settings,
        ).pack(side="left")
        ctk.CTkButton(
            footer,
            text=icon_label("ok", "Got it"),
            fg_color=PRIMARY_FG,
            hover_color=PRIMARY_HOVER,
            corner_radius=12,
            command=self._close,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close)
        center_on_parent(self, master, width=740, height=660)

    def _open_settings(self):
        callback = self.on_open_settings
        self._close()
        if callback:
            callback()

    def _close(self):
        if self.on_close_cb:
            self.on_close_cb()
        self.destroy()


# --- Settings window ------------------------------------------------------------

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, on_saved=None):
        super().__init__(master)
        self.title("IBKR Trade Alerts - Settings")
        self.minsize(700, 760)
        self.transient(master)
        self.on_saved = on_saved
        self.app_config = load_config()
        self.load_env_file()
        self.exception_rows = []
        self.shortcut_rows = []

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(side="bottom", fill="x", padx=14, pady=12)
        ctk.CTkButton(
            button_frame,
            text=icon_label("save", "Save"),
            fg_color=SUCCESS_FG,
            hover_color=SUCCESS_HOVER,
            corner_radius=12,
            command=self.save_config,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            button_frame,
            text=icon_label("test", "Test Telegram"),
            fg_color=PRIMARY_FG,
            hover_color=PRIMARY_HOVER,
            corner_radius=12,
            command=self.test_telegram,
        ).pack(side="left", padx=(0, 8))
        icon_button(button_frame, "help", self.open_help, tooltip="Help").pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            button_frame,
            text=icon_label("cancel", "Close"),
            fg_color=SECONDARY_FG,
            hover_color=SECONDARY_HOVER,
            text_color=SECONDARY_TEXT_FG,
            corner_radius=12,
            command=self.destroy,
        ).pack(side="right")

        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=14,
            fg_color=CARD_FG,
            segmented_button_selected_color=PRIMARY_FG,
            segmented_button_selected_hover_color=PRIMARY_HOVER,
            segmented_button_unselected_color=SECONDARY_FG,
        )
        self.tabview.pack(fill="both", expand=True, padx=14, pady=(14, 0))

        for name in ("Telegram", "IBKR", "Assets", "Percentages", "Room", "Shortcuts", "Messages"):
            self.tabview.add(name)

        self.create_telegram_tab(self.tabview.tab("Telegram"))
        self.create_ibkr_tab(self.tabview.tab("IBKR"))
        self.create_assets_tab(self.tabview.tab("Assets"))
        self.create_percentages_tab(self.tabview.tab("Percentages"))
        self.create_room_tab(self.tabview.tab("Room"))
        self.create_shortcuts_tab(self.tabview.tab("Shortcuts"))
        self.create_messages_tab(self.tabview.tab("Messages"))

        center_on_parent(self, master, width=800, height=820)

    def open_help(self):
        HelpWindow(self)

    def load_env_file(self):
        self.env_vars = read_env_values()

    def _env_bool(self, key, default=False):
        value = self.env_vars.get(key)
        if value is None:
            return default
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

    def _scrollable(self, tab):
        panel = ScrollPanel(tab, window=self)
        panel.pack(fill="both", expand=True, padx=4, pady=4)
        return panel.body

    @staticmethod
    def _heading(parent, text):
        return ctk.CTkLabel(parent, text=text, font=ui_font(14, "bold"), text_color=PRIMARY_FG, anchor="w")

    @staticmethod
    def _muted(parent, text, wraplength=560):
        return ctk.CTkLabel(
            parent, text=text, font=ui_font(10), text_color=HINT_FG,
            anchor="w", justify="left", wraplength=wraplength,
        )

    # -- Telegram --
    def create_telegram_tab(self, tab):
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        self._heading(frame, "Telegram Bot Configuration").grid(row=0, column=0, columnspan=2, pady=10, sticky="w")
        self._muted(
            frame,
            "Tokens are saved to secrets.env (gitignored). Connection settings stay in .env. Templates stay in messages.env.",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ctk.CTkLabel(frame, text="Bot Token:", text_color=TEXT_FG).grid(row=2, column=0, sticky="w", pady=5)
        self.telegram_token = make_entry(frame, width=340, show="*")
        self.telegram_token.insert(0, self.env_vars.get('TELEGRAM_BOT_TOKEN', ''))
        self.telegram_token.grid(row=2, column=1, padx=10)
        ctk.CTkLabel(frame, text="Chat/Channel ID:", text_color=TEXT_FG).grid(row=3, column=0, sticky="w", pady=5)
        self.telegram_chat_id = make_entry(frame, width=340)
        self.telegram_chat_id.insert(0, self.env_vars.get('TELEGRAM_CHAT_ID', ''))
        self.telegram_chat_id.grid(row=3, column=1, padx=10)

    # -- IBKR --
    def create_ibkr_tab(self, tab):
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        self._heading(frame, "IBKR Connection Settings").grid(row=0, column=0, columnspan=2, pady=10, sticky="w")

        ctk.CTkLabel(frame, text="Host:", text_color=TEXT_FG).grid(row=1, column=0, sticky="w", pady=5)
        self.ibkr_host = make_entry(frame, width=260)
        self.ibkr_host.insert(0, self.env_vars.get('IBKR_HOST', '127.0.0.1'))
        self.ibkr_host.grid(row=1, column=1, padx=10, sticky="w")

        ctk.CTkLabel(frame, text="Port:", text_color=TEXT_FG).grid(row=2, column=0, sticky="w", pady=5)
        self.ibkr_port = make_entry(frame, width=260)
        self.ibkr_port.insert(0, self.env_vars.get('IBKR_PORT', '7496'))
        self.ibkr_port.grid(row=2, column=1, padx=10, sticky="w")

        ctk.CTkLabel(frame, text="Client ID:", text_color=TEXT_FG).grid(row=3, column=0, sticky="w", pady=5)
        self.ibkr_client_id = make_entry(frame, width=260)
        self.ibkr_client_id.insert(0, self.env_vars.get('IBKR_CLIENT_ID', '0') or '0')
        self.ibkr_client_id.grid(row=3, column=1, padx=10, sticky="w")

        self.auto_stop_enabled = ctk.BooleanVar(value=self._env_bool('AUTO_STOP_ENABLED', default=True))
        ctk.CTkCheckBox(
            frame, text="Enable Auto-Stop", variable=self.auto_stop_enabled,
            command=self._toggle_auto_stop_fields, text_color=TEXT_FG,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 5))

        ctk.CTkLabel(frame, text="Auto-Stop Time (HH:MM):", text_color=TEXT_FG).grid(row=5, column=0, sticky="w", pady=5)
        self.stop_time = make_entry(frame, width=260)
        self.stop_time.insert(0, self.env_vars.get('STOP_TIME', '16:00') or '16:00')
        self.stop_time.grid(row=5, column=1, padx=10, sticky="w")
        self._toggle_auto_stop_fields()

        help_box = make_textbox(frame, height=110, width=560, fg_color=CARD_FG, corner_radius=12)
        help_box.insert(
            "1.0",
            "Gateway ports: 4001 live / 4002 paper\n"
            "TWS ports: 7496 live / 7497 paper\n"
            "Use Client ID 0 + Master API Client ID 0 to receive manual orders.\n"
            "Click Help for the full first-use checklist.",
        )
        help_box.configure(state="disabled")
        help_box.grid(row=6, column=0, columnspan=2, pady=16, sticky="ew")

    def _toggle_auto_stop_fields(self):
        self.stop_time.configure(state="normal" if self.auto_stop_enabled.get() else "disabled")

    # -- Assets --
    def create_assets_tab(self, tab):
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        self._heading(frame, "Monitor These Markets").pack(anchor="w", pady=10)
        self._muted(frame, "Disable a type to skip Telegram alerts for that market.").pack(anchor="w", pady=(0, 12))

        self.monitor_stocks = ctk.BooleanVar(value=self.app_config.get("monitor_stocks", True))
        self.monitor_options = ctk.BooleanVar(value=self.app_config.get("monitor_options", True))
        self.monitor_futures = ctk.BooleanVar(value=self.app_config.get("monitor_futures", True))
        self.notify_order_submitted = ctk.BooleanVar(value=self.app_config.get("notify_order_submitted", True))

        ctk.CTkCheckBox(frame, text="Stocks", variable=self.monitor_stocks, text_color=TEXT_FG).pack(anchor="w", pady=4)
        ctk.CTkCheckBox(
            frame, text="Options (including futures options)", variable=self.monitor_options, text_color=TEXT_FG,
        ).pack(anchor="w", pady=4)
        ctk.CTkCheckBox(frame, text="Futures", variable=self.monitor_futures, text_color=TEXT_FG).pack(anchor="w", pady=4)

        ctk.CTkFrame(frame, height=1, fg_color=BORDER_FG).pack(fill="x", pady=16)
        self._heading(frame, "Order Alerts").pack(anchor="w", pady=(0, 8))
        ctk.CTkCheckBox(
            frame,
            text="Send alerts when orders are submitted",
            variable=self.notify_order_submitted,
            text_color=TEXT_FG,
        ).pack(anchor="w", pady=4)
        self._muted(frame, "Turn this off to only receive filled-order messages.").pack(anchor="w", pady=(4, 0))

        ctk.CTkFrame(frame, height=1, fg_color=BORDER_FG).pack(fill="x", pady=16)
        self._heading(frame, "Appearance").pack(anchor="w", pady=(0, 8))
        self._muted(frame, "Font size applies after you Save (restart companion if some labels look mixed).").pack(
            anchor="w", pady=(0, 8)
        )
        size_row = ctk.CTkFrame(frame, fg_color="transparent")
        size_row.pack(anchor="w", fill="x")
        ctk.CTkLabel(size_row, text="UI font size:", text_color=TEXT_FG).pack(side="left", padx=(0, 10))
        current_size = int(self.app_config.get("ui_font_size", 13) or 13)
        # Map stored point size to a friendly label
        label_for_size = {11: "Small", 13: "Medium", 15: "Large", 17: "Extra large"}
        closest = min(label_for_size.keys(), key=lambda s: abs(s - current_size))
        self.ui_font_size_label = ctk.StringVar(value=label_for_size[closest])
        self._font_size_map = {"Small": 11, "Medium": 13, "Large": 15, "Extra large": 17}
        ctk.CTkOptionMenu(
            size_row,
            variable=self.ui_font_size_label,
            values=["Small", "Medium", "Large", "Extra large"],
            width=160,
            fg_color=SECONDARY_FG,
            button_color=SECONDARY_HOVER,
            button_hover_color=SECONDARY_HOVER,
            text_color=SECONDARY_TEXT_FG,
        ).pack(side="left")

    # -- Percentages --
    def create_percentages_tab(self, tab):
        frame = self._scrollable(tab)
        self._heading(frame, "100% Size Baselines").grid(row=0, column=0, columnspan=4, sticky="w", pady=8, padx=12)
        self._muted(
            frame,
            "Set what 100% means for each asset type. Add symbol exceptions (e.g. GLD options = 8 contracts).",
            wraplength=640,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 12), padx=12)

        defaults = self.app_config["percentages"]["defaults"]
        self.default_vars = {}
        row = 2
        for asset, title in (("stock", "Stocks default"), ("option", "Options default"), ("future", "Futures default")):
            ctk.CTkLabel(frame, text=title, font=ui_font(11, "bold"), text_color=TEXT_FG).grid(
                row=row, column=0, sticky="w", pady=6, padx=12
            )
            unit_var = ctk.StringVar(value=defaults[asset]["unit"])
            value_var = ctk.StringVar(value=str(defaults[asset]["value"]))
            self.default_vars[asset] = {"unit": unit_var, "value": value_var}
            ctk.CTkOptionMenu(
                frame, variable=unit_var, values=["quantity", "dollars"], width=130,
                fg_color=SECONDARY_FG, button_color=SECONDARY_HOVER, button_hover_color=SECONDARY_HOVER,
                text_color=SECONDARY_TEXT_FG,
            ).grid(row=row, column=1, padx=6)
            make_entry(frame, textvariable=value_var, width=110).grid(row=row, column=2, padx=6)
            ctk.CTkLabel(frame, text="quantity = shares/contracts", font=ui_font(10), text_color=HINT_FG).grid(
                row=row, column=3, sticky="w"
            )
            row += 1

        ctk.CTkFrame(frame, height=1, fg_color=BORDER_FG).grid(row=row, column=0, columnspan=4, sticky="ew", pady=12, padx=12)
        row += 1
        self._heading(frame, "Symbol Exceptions").grid(row=row, column=0, columnspan=4, sticky="w", padx=12)
        row += 1

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=row, column=0, columnspan=4, sticky="ew", pady=4, padx=12)
        for i, text in enumerate(("Symbol", "Asset", "Unit", "100% Value", "")):
            ctk.CTkLabel(header, text=text, width=110 if i < 4 else 40, font=ui_font(10, "bold"), text_color=HINT_FG).grid(
                row=0, column=i, padx=3
            )
        row += 1

        self.exceptions_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self.exceptions_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=12)
        row += 1

        ctk.CTkButton(
            frame,
            text=icon_label("add", "Add Exception"),
            fg_color=SECONDARY_FG,
            hover_color=SECONDARY_HOVER,
            text_color=SECONDARY_TEXT_FG,
            corner_radius=10,
            command=self._add_exception_row,
        ).grid(row=row, column=0, sticky="w", pady=8, padx=12)

        for item in self.app_config["percentages"].get("exceptions", []):
            self._add_exception_row(item)

    def _add_exception_row(self, data=None):
        data = data or {"symbol": "", "asset": "any", "unit": "quantity", "value": ""}
        row_frame = ctk.CTkFrame(self.exceptions_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=3)

        symbol_var = ctk.StringVar(value=data.get("symbol", ""))
        asset_var = ctk.StringVar(value=data.get("asset", "any"))
        unit_var = ctk.StringVar(value=data.get("unit", "quantity"))
        value_var = ctk.StringVar(value=str(data.get("value", "")))

        make_entry(row_frame, textvariable=symbol_var, width=110).grid(row=0, column=0, padx=3)
        ctk.CTkOptionMenu(
            row_frame, variable=asset_var, values=["any", "stock", "option", "future"], width=110,
            fg_color=SECONDARY_FG, button_color=SECONDARY_HOVER, button_hover_color=SECONDARY_HOVER,
            text_color=SECONDARY_TEXT_FG,
        ).grid(row=0, column=1, padx=3)
        ctk.CTkOptionMenu(
            row_frame, variable=unit_var, values=["quantity", "dollars"], width=110,
            fg_color=SECONDARY_FG, button_color=SECONDARY_HOVER, button_hover_color=SECONDARY_HOVER,
            text_color=SECONDARY_TEXT_FG,
        ).grid(row=0, column=2, padx=3)
        make_entry(row_frame, textvariable=value_var, width=110).grid(row=0, column=3, padx=3)

        row_data = {"frame": row_frame, "symbol": symbol_var, "asset": asset_var, "unit": unit_var, "value": value_var}

        def remove():
            row_frame.destroy()
            self.exception_rows.remove(row_data)

        ctk.CTkButton(
            row_frame, text=ICONS["remove"], width=32, height=28, corner_radius=8,
            fg_color=DANGER_FG, hover_color=DANGER_HOVER, command=remove,
        ).grid(row=0, column=4, padx=3)
        self.exception_rows.append(row_data)

    # -- Room --
    def create_room_tab(self, tab):
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        room = room_settings(self.app_config)

        self._heading(frame, "Channel Room Controls").pack(anchor="w", pady=(0, 8))
        self._muted(
            frame,
            (
                "OPEN ROOM / CLOSE ROOM rename your Telegram channel to:\n"
                "  {current name} - ROOM OPEN\n"
                "  {current name} - ROOM CLOSED\n\n"
                "The base name is kept; only the status suffix changes.\n\n"
                "Telegram does not allow bots to mute channel notifications before a rename "
                "(no silent mode for title changes). This app instead deletes the automatic "
                "“name changed” notice as quickly as possible.\n\n"
                "Bot must be channel admin with: Change Channel Info + Delete Messages."
            ),
            wraplength=620,
        ).pack(anchor="w", pady=(0, 14))

        form = ctk.CTkFrame(frame, fg_color="transparent")
        form.pack(anchor="w", fill="x")

        self.room_open_button = ctk.StringVar(value=room["open_button"])
        self.room_close_button = ctk.StringVar(value=room["close_button"])
        self.room_open_text = ctk.StringVar(value=room["open_text"])
        self.room_closed_text = ctk.StringVar(value=room["closed_text"])

        rows = [
            ("Open button label", self.room_open_button),
            ("Close button label", self.room_close_button),
            ("Open status text (in channel name)", self.room_open_text),
            ("Closed status text (in channel name)", self.room_closed_text),
        ]
        for i, (label, var) in enumerate(rows):
            ctk.CTkLabel(form, text=label + ":", text_color=TEXT_FG).grid(row=i, column=0, sticky="w", pady=6)
            make_entry(form, textvariable=var, width=300).grid(row=i, column=1, sticky="w", padx=10, pady=6)

        self._muted(
            frame,
            'Example: base "My Desk" + open text "ROOM OPEN" → "My Desk - ROOM OPEN"',
            wraplength=620,
        ).pack(anchor="w", pady=(16, 0))

    # -- Shortcuts --
    def create_shortcuts_tab(self, tab):
        frame = self._scrollable(tab)
        self._heading(frame, "Companion Shortcut Buttons").pack(anchor="w", pady=8, padx=12)
        self._muted(
            frame,
            "These appear on the companion window and send a Telegram message when clicked.",
            wraplength=640,
        ).pack(anchor="w", pady=(0, 10), padx=12)

        self.shortcuts_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self.shortcuts_frame.pack(fill="x", padx=12)
        ctk.CTkButton(
            frame,
            text=icon_label("add", "Add Shortcut"),
            fg_color=SECONDARY_FG,
            hover_color=SECONDARY_HOVER,
            text_color=SECONDARY_TEXT_FG,
            corner_radius=10,
            command=self._add_shortcut_row,
        ).pack(anchor="w", pady=8, padx=12)

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

        self._heading(frame, "Summary Indicators").pack(anchor="w", pady=(16, 4), padx=12)
        self._muted(
            frame,
            (
                "For each shortcut, choose whether it counts toward the summary when pressed: "
                "Green trade, Red trade, or Close trade (trades taken only). "
                "You can assign multiple shortcuts to the same role. Leave as None for normal shortcuts."
            ),
            wraplength=640,
        ).pack(anchor="w", pady=(0, 4), padx=12)
        self._muted(
            frame,
            (
                "Trade ID: check “Increment trade ID” on one or more shortcuts (e.g. Starting Trade). "
                "Use {cnt} in message templates / shortcut text for the number-emoji ID (1️⃣4️⃣). "
                "Use {textbox} for a shared 10-character field in the Shortcuts corner (all {textbox} use the same value)."
            ),
            wraplength=640,
        ).pack(anchor="w", pady=(0, 8), padx=12)

    def _add_shortcut_row(self, data=None):
        data = data or {
            "id": "",
            "label": "",
            "message": "",
            "summary_role": "none",
            "increment_counter": False,
        }
        row_card, row_frame = section_card(self.shortcuts_frame, "Shortcut")
        row_card.pack(fill="x", pady=6)

        label_var = ctk.StringVar(value=data.get("label", ""))
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
        role_var = ctk.StringVar(value=role_labels[role_value])
        increment_var = ctk.BooleanVar(value=bool(data.get("increment_counter")))

        ctk.CTkLabel(row_frame, text="Button label:", text_color=TEXT_FG).grid(row=0, column=0, sticky="w")
        make_entry(row_frame, textvariable=label_var, width=280).grid(row=0, column=1, sticky="w", padx=6)
        ctk.CTkLabel(row_frame, text="Telegram message:", text_color=TEXT_FG).grid(row=1, column=0, sticky="nw", pady=4)
        msg_box = make_textbox(row_frame, height=70, width=420)
        msg_box.insert("1.0", data.get("message", ""))
        msg_box.grid(row=1, column=1, sticky="w", padx=6, pady=4)

        ctk.CTkLabel(row_frame, text="Summary indicator:", text_color=TEXT_FG).grid(row=2, column=0, sticky="w", pady=(4, 0))
        ctk.CTkOptionMenu(
            row_frame,
            variable=role_var,
            values=tuple(role_labels.values()),
            width=160,
            fg_color=SECONDARY_FG, button_color=SECONDARY_HOVER, button_hover_color=SECONDARY_HOVER,
            text_color=SECONDARY_TEXT_FG,
        ).grid(row=2, column=1, sticky="w", padx=6, pady=(4, 0))
        ctk.CTkCheckBox(
            row_frame,
            text="Increment trade ID",
            variable=increment_var,
            text_color=TEXT_FG,
        ).grid(row=3, column=1, sticky="w", padx=6, pady=(6, 0))

        row_data = {
            "frame": row_card,
            "id": id_value,
            "label": label_var,
            "message_box": msg_box,
            "summary_role": role_var,
            "summary_role_map": label_to_role,
            "increment_counter": increment_var,
        }

        def remove():
            row_card.destroy()
            self.shortcut_rows.remove(row_data)

        ctk.CTkButton(
            row_frame, text="Remove", fg_color=DANGER_FG, hover_color=DANGER_HOVER, corner_radius=10,
            width=90, command=remove,
        ).grid(row=0, column=2, padx=6)
        self.shortcut_rows.append(row_data)

    # -- Messages --
    def create_messages_tab(self, tab):
        frame = self._scrollable(tab)
        self._heading(frame, "Message Templates").grid(row=0, column=0, sticky="w", pady=8, padx=12)

        guide = make_textbox(frame, height=280, width=680, fg_color=CARD_FG, corner_radius=12)
        guide.insert("1.0", MESSAGE_GUIDE)
        guide.configure(state="disabled")
        guide.grid(row=1, column=0, sticky="ew", pady=6, padx=12)

        templates = [
            ("Order Submitted (Stock)", "order_message", "ORDER_MESSAGE", DEFAULT_ORDER_MESSAGE, 110),
            ("Order Submitted (Option)", "order_option_message", "ORDER_OPTION_MESSAGE", DEFAULT_ORDER_OPTION_MESSAGE, 130),
            ("Order Submitted (Futures)", "order_future_message", "ORDER_FUTURE_MESSAGE", DEFAULT_ORDER_FUTURE_MESSAGE, 130),
            ("Order Filled (Stock)", "trade_message", "TRADE_MESSAGE", DEFAULT_TRADE_MESSAGE, 110),
            ("Order Filled (Option)", "option_message", "OPTION_MESSAGE", DEFAULT_OPTION_MESSAGE, 130),
            ("Order Filled (Futures)", "future_message", "FUTURE_MESSAGE", DEFAULT_FUTURE_MESSAGE, 130),
            ("Summary", "summary_message", "SUMMARY_MESSAGE", DEFAULT_SUMMARY_MESSAGE, 110),
            ("Long-term Summary", "long_term_summary_message", "LONG_TERM_SUMMARY_MESSAGE", DEFAULT_LONG_TERM_SUMMARY_MESSAGE, 110),
        ]

        row = 2
        for title, attr, env_key, default, height in templates:
            ctk.CTkLabel(frame, text=title, font=ui_font(11, "bold"), text_color=TEXT_FG).grid(
                row=row, column=0, sticky="w", pady=(10, 2), padx=12
            )
            row += 1
            box = make_textbox(frame, height=height, width=680)
            box.insert("1.0", self.env_vars.get(env_key) or default)
            box.grid(row=row, column=0, sticky="ew", pady=2, padx=12)
            setattr(self, attr, box)
            row += 1

        ctk.CTkLabel(frame, text="Connected Message:", font=ui_font(11, "bold"), text_color=TEXT_FG).grid(
            row=row, column=0, sticky="w", pady=(10, 2), padx=12
        )
        row += 1
        self.connected_message = make_entry(frame, width=680)
        self.connected_message.insert(0, self.env_vars.get('CONNECTED_MESSAGE') or '✅ Connected to IBKR. Ready for trades.')
        self.connected_message.grid(row=row, column=0, sticky="ew", padx=12)
        row += 1

        ctk.CTkLabel(frame, text="Market Closed Message:", font=ui_font(11, "bold"), text_color=TEXT_FG).grid(
            row=row, column=0, sticky="w", pady=(10, 2), padx=12
        )
        row += 1
        self.closed_message = make_entry(frame, width=680)
        self.closed_message.insert(0, self.env_vars.get('CLOSED_MESSAGE') or '📊 Market closed. Trade monitor stopping.')
        self.closed_message.grid(row=row, column=0, sticky="ew", padx=12, pady=(0, 16))

    # -- Save / test --
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
            "ui_font_size": self._font_size_map.get(
                self.ui_font_size_label.get(),
                existing.get("ui_font_size", 13),
            ) if hasattr(self, "ui_font_size_label") else existing.get("ui_font_size", 13),
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
                "Settings saved.\nConnection → env/.env\nMessages → env/messages.env\nSecrets → env/secrets.env\n"
                "Font size updates the next time you open Settings / restart the companion.",
            )
            if self.on_saved:
                self.on_saved()
            # Apply font size for subsequent widgets in this session
            set_ui_font_size(app_config.get("ui_font_size", 13))
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


# --- Companion window ------------------------------------------------------------

class CompanionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("IBKR Trade Alerts")
        self.root.minsize(440, 560)
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

        apply_appearance(bool(self.app_config.get("dark_mode")))
        set_ui_font_size(self.app_config.get("ui_font_size", 13))
        saved_geom = str(self.app_config.get("window_geometry") or "").strip()
        self.root.geometry(saved_geom if saved_geom else "560x820")

        # —— Header ——
        self.header = ctk.CTkFrame(root, corner_radius=0, fg_color=HEADER_FG)
        self.header.pack(fill="x")
        header_top = ctk.CTkFrame(self.header, fg_color="transparent")
        header_top.pack(fill="x", padx=20, pady=(16, 0))
        title_block = ctk.CTkFrame(header_top, fg_color="transparent")
        title_block.pack(side="left", fill="x", expand=True)
        self.title_label = ctk.CTkLabel(
            title_block,
            text=icon_label("app", "IBKR Trade Alerts"),
            text_color="#FFFFFF",
            font=ui_font(18, "bold"),
            anchor="w",
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = ctk.CTkLabel(
            title_block,
            text="Companion · Telegram alerts · IBKR",
            text_color=HEADER_SUB_FG,
            font=ui_font(10),
            anchor="w",
        )
        self.subtitle_label.pack(anchor="w", pady=(2, 0))
        self.theme_btn = ctk.CTkButton(
            header_top,
            text=self._theme_button_label(),
            fg_color=HEADER_BTN_FG,
            hover_color=HEADER_BTN_HOVER,
            text_color="#FFFFFF",
            corner_radius=10,
            width=92,
            command=self.toggle_dark_mode,
        )
        self.theme_btn.pack(side="right")

        status_row = ctk.CTkFrame(self.header, fg_color="transparent")
        status_row.pack(fill="x", padx=20, pady=(12, 16))
        self.status_chip = ctk.CTkFrame(status_row, fg_color=CHIP_FG, corner_radius=12)
        self.status_chip.pack(side="left")
        chip_inner = ctk.CTkFrame(self.status_chip, fg_color="transparent")
        chip_inner.pack(padx=10, pady=4)
        self.status_dot = ctk.CTkLabel(chip_inner, text="●", text_color=HINT_FG, font=ui_font(9))
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_label = ctk.CTkLabel(chip_inner, text="Idle", text_color=CHIP_TEXT_FG, font=ui_font(10, "bold"))
        self.status_label.pack(side="left")

        # —— Controls ——
        controls = ctk.CTkFrame(root, fg_color="transparent")
        controls.pack(fill="x", padx=16, pady=(12, 8))
        self.start_btn = ctk.CTkButton(
            controls,
            text=icon_label("start", "Start Monitoring"),
            fg_color=SUCCESS_FG,
            hover_color=SUCCESS_HOVER,
            corner_radius=12,
            command=self.start_monitoring,
        )
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ctk.CTkButton(
            controls,
            text=icon_label("stop", "Stop"),
            fg_color=DANGER_FG,
            hover_color=DANGER_HOVER,
            corner_radius=12,
            state="disabled",
            command=self.stop_monitoring,
        )
        self.stop_btn.pack(side="left")
        self.help_btn = icon_button(controls, "help", self.open_help, tooltip="Help")
        self.help_btn.pack(side="right")
        self.settings_btn = icon_button(controls, "settings", self.open_settings, tooltip="Settings")
        self.settings_btn.pack(side="right", padx=(0, 8))

        # —— Scrollable body (room / summary / shortcuts) ——
        self.scroll = ScrollPanel(root, window=root, full_window_wheel=True)
        self.scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        scroll_body = self.scroll.body

        # Room
        self.room_card, room_inner = section_card(scroll_body, icon_label("room", "Room"))
        self.room_card.pack(fill="x", pady=(0, 12))
        self.room_btns = ctk.CTkFrame(room_inner, fg_color="transparent")
        self.room_btns.pack(fill="x")
        self.open_room_btn = ctk.CTkButton(
            self.room_btns, text="OPEN ROOM", fg_color=SUCCESS_FG, hover_color=SUCCESS_HOVER,
            corner_radius=12, command=lambda: self.set_room(True),
        )
        self.close_room_btn = ctk.CTkButton(
            self.room_btns, text="CLOSE ROOM", fg_color=DANGER_FG, hover_color=DANGER_HOVER,
            corner_radius=12, command=lambda: self.set_room(False),
        )
        self.room_hint = make_wrap_label(room_inner, text="", pad=4)
        self.room_hint.pack(anchor="w", fill="x", pady=(10, 0))

        # Summary
        self.summary_card, summary_inner = section_card(scroll_body, icon_label("summary", "Summary"))
        self.summary_card.pack(fill="x", pady=(0, 12))
        self.summary_btns = ctk.CTkFrame(summary_inner, fg_color="transparent")
        self.summary_btns.pack(fill="x")
        self._summary_buttons = [
            ctk.CTkButton(
                self.summary_btns, text=icon_label("summary", "Summary"), fg_color=PRIMARY_FG,
                hover_color=PRIMARY_HOVER, corner_radius=12,
                command=lambda: self.preview_and_send_summary("session"),
            ),
            ctk.CTkButton(
                self.summary_btns, text=icon_label("reset", "Reset"), fg_color=SECONDARY_FG,
                hover_color=SECONDARY_HOVER, text_color=SECONDARY_TEXT_FG, corner_radius=12,
                command=lambda: self.reset_trade_summary("session"),
            ),
            ctk.CTkButton(
                self.summary_btns, text=icon_label("long_term", "Long-term"), fg_color=PRIMARY_FG,
                hover_color=PRIMARY_HOVER, corner_radius=12,
                command=lambda: self.preview_and_send_summary("long_term"),
            ),
            ctk.CTkButton(
                self.summary_btns, text=icon_label("reset", "Reset LT"), fg_color=SECONDARY_FG,
                hover_color=SECONDARY_HOVER, text_color=SECONDARY_TEXT_FG, corner_radius=12,
                command=lambda: self.reset_trade_summary("long_term"),
            ),
        ]
        self.summary_hint = make_wrap_label(summary_inner, text="", pad=4)
        self.summary_hint.pack(anchor="w", fill="x", pady=(10, 0))
        counter_row = ctk.CTkFrame(summary_inner, fg_color="transparent")
        counter_row.pack(fill="x", pady=(10, 0))
        self.counter_hint = make_wrap_label(counter_row, text="", pad=4)
        self.counter_hint.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            counter_row, text=icon_label("reset", "Reset ID"), fg_color=SECONDARY_FG,
            hover_color=SECONDARY_HOVER, text_color=SECONDARY_TEXT_FG, corner_radius=12,
            command=self.reset_trade_id,
        ).pack(side="right", padx=(8, 0))
        self.summary_help = make_wrap_label(
            summary_inner,
            text="Green / Red / Close shortcuts update counts. Trade ID increments from mapped shortcuts — use {cnt} in templates.",
            pad=4,
        )
        self.summary_help.pack(anchor="w", fill="x", pady=(8, 0))
        self.refresh_summary_label()

        # Shortcuts
        self.shortcuts_card, shortcuts_inner = section_card(scroll_body, icon_label("shortcuts", "Shortcuts"))
        self.shortcuts_card.pack(fill="x", pady=(0, 12))
        shortcuts_top = ctk.CTkFrame(shortcuts_inner, fg_color="transparent")
        shortcuts_top.pack(fill="x", pady=(0, 8))
        self.shortcuts_textbox_bar = ctk.CTkFrame(shortcuts_top, fg_color="transparent")
        ctk.CTkLabel(
            self.shortcuts_textbox_bar, text="{textbox}:", text_color=HINT_FG, font=ui_font(10),
        ).pack(side="left", padx=(0, 6))
        self.shortcut_textbox = ctk.CTkEntry(self.shortcuts_textbox_bar, width=120, placeholder_text="10 chars max")

        def _clip_shortcut_textbox(_event=None):
            value = self.shortcut_textbox.get()
            if len(value) > TEXTBOX_MAX_LEN:
                self.shortcut_textbox.delete(0, "end")
                self.shortcut_textbox.insert(0, value[:TEXTBOX_MAX_LEN])

        self.shortcut_textbox.bind("<KeyRelease>", _clip_shortcut_textbox, add="+")
        self.shortcut_textbox.pack(side="left")
        self.shortcuts_container = ctk.CTkFrame(shortcuts_inner, fg_color="transparent")
        self.shortcuts_container.pack(fill="x")
        self.shortcuts_hint = make_wrap_label(
            shortcuts_inner,
            text="Widen the window to arrange shortcuts in a multi-column grid.",
            pad=4,
        )
        self.shortcuts_hint.pack(anchor="w", fill="x", pady=(10, 0))

        # Activity stays below the scroll area so trackpad scrolling isn't blocked by the log textbox
        self.activity_card, activity_inner = section_card(root, icon_label("activity", "Activity"))
        self.activity_card.pack(fill="x", padx=16, pady=(0, 16))
        self.log = ctk.CTkTextbox(
            activity_inner,
            height=160,
            wrap="word",
            corner_radius=10,
            border_width=0,
            fg_color=LOG_BG,
            text_color=LOG_FG,
            font=ui_font(10),
        )
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")
        self.log._textbox.tag_configure("ok", foreground=LOG_OK)
        self.log._textbox.tag_configure("err", foreground=LOG_ERR)
        self.log._textbox.tag_configure("info", foreground=LOG_INFO)

        self.scroll.set_block_widgets([self.log])

        self.refresh_shortcuts()
        self.refresh_room_controls()
        self._relayout(force=True)
        self.scroll.refresh()
        self._set_status("Idle", "idle")

        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self.root.after(200, self._drain_status_queue)
        self.append_log("Companion ready. Open Help for first-use IBKR setup, then Start Monitoring.", "info")
        self.root.after(400, self._maybe_show_first_use_guide)
        self.title_cleaner.start()

    def _theme_button_label(self):
        return icon_label("light", "Light") if is_dark_mode() else icon_label("dark", "Dark")

    def _set_status(self, text, kind="idle"):
        self.status_label.configure(text=text)
        self.status_dot.configure(text_color=STATUS_DOT_COLORS.get(kind, HINT_FG))

    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        if self._layout_after:
            self.root.after_cancel(self._layout_after)
        self._layout_after = self.root.after(80, lambda: self._relayout(force=False))
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
        apply_appearance(dark)
        cfg = load_config()
        cfg["dark_mode"] = dark
        save_config(cfg)
        self.app_config = cfg
        self.theme_btn.configure(text=self._theme_button_label())
        self.append_log("Switched to dark mode." if dark else "Switched to light mode.", "info")

    def _relayout(self, force=False):
        self._layout_after = None
        try:
            width = max(self.scroll.canvas.winfo_width(), 1)
        except tk.TclError:
            width = max(self.root.winfo_width(), 1)

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
            self.open_room_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self.close_room_btn.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        else:
            self.open_room_btn.pack(fill="x", pady=(0, 8))
            self.close_room_btn.pack(fill="x")

        # Summary: 1x4 when wide, else 2x2
        summary_wide = width >= 700
        if force or summary_wide != self._last_summary_wide:
            self._last_summary_wide = summary_wide
            for btn in self._summary_buttons:
                btn.grid_forget()
            cols = 4 if summary_wide else 2
            for i in range(max(cols, 4)):
                self.summary_btns.columnconfigure(i, weight=1 if i < cols else 0)
            for i, btn in enumerate(self._summary_buttons):
                r, c = divmod(i, cols)
                pad_x = (0, 8) if c < cols - 1 else (0, 0)
                pad_y = (0, 8) if r == 0 and cols == 2 else (0, 0)
                btn.grid(row=r, column=c, sticky="ew", padx=pad_x, pady=pad_y)

        # Shortcuts grid
        cols = grid_columns_for_width(width)
        if not self._shortcut_buttons:
            self.scroll.refresh()
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
            btn.grid(row=r, column=c, sticky="ew", padx=5, pady=5)
        self.scroll.refresh()

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
        self.open_room_btn.configure(text=room["open_button"])
        self.close_room_btn.configure(text=room["close_button"])
        self.room_hint.configure(
            text=f'Names become:  … - {room["open_text"]}   /   … - {room["closed_text"]}'
        )

    def _shortcut_textbox_value(self):
        try:
            return self.shortcut_textbox.get()
        except (tk.TclError, AttributeError):
            return ""

    def _sync_shortcut_textbox(self, shortcuts):
        if shortcuts_use_textbox(shortcuts):
            self.shortcuts_textbox_bar.pack(side="right")
        else:
            self.shortcuts_textbox_bar.pack_forget()

    def refresh_shortcuts(self):
        for child in self.shortcuts_container.winfo_children():
            child.destroy()
        self._shortcut_buttons = []
        self._last_shortcut_cols = None
        self.app_config = load_config()
        self.refresh_room_controls()
        shortcuts = self.app_config.get("shortcuts") or []
        self._sync_shortcut_textbox(shortcuts)
        if not shortcuts:
            ctk.CTkLabel(
                self.shortcuts_container, text="No shortcuts configured.", text_color=HINT_FG, font=ui_font(10),
            ).grid(row=0, column=0, sticky="w")
            return
        for item in shortcuts:
            btn = ctk.CTkButton(
                self.shortcuts_container,
                text=item.get("label", "Shortcut"),
                fg_color=PRIMARY_FG,
                hover_color=PRIMARY_HOVER,
                corner_radius=12,
                command=lambda shortcut=item: self.send_shortcut(shortcut),
            )
            self._shortcut_buttons.append(btn)
        self._relayout(force=True)

    def set_room(self, is_open):
        reload_env()
        self.open_room_btn.configure(state="disabled")
        self.close_room_btn.configure(state="disabled")
        self.append_log("Updating channel room status...", "info")

        def work():
            ok, title, detail = set_room_state(is_open)
            self.root.after(0, lambda: self._room_done(ok, title, detail))

        threading.Thread(target=work, daemon=True).start()

    def _room_done(self, ok, title, detail):
        self.open_room_btn.configure(state="normal")
        self.close_room_btn.configure(state="normal")
        if ok:
            self.append_log(detail, "ok")
            if title:
                self.append_log(f"Channel title: {title}", "info")
        else:
            self.append_log(detail, "err")
            show_error(self.root, "Room update failed", detail)

    def send_shortcut(self, shortcut, textbox_text=None):
        if isinstance(shortcut, str):
            shortcut = {"message": shortcut, "id": "", "label": "Shortcut"}
        message = shortcut.get("message", "")
        if textbox_text is None:
            textbox_text = self._shortcut_textbox_value() if message_uses_textbox(message) else ""
        message = apply_textbox_placeholder(message, textbox_text)
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
        self.summary_hint.configure(text=summary_label_text())
        if hasattr(self, "counter_hint"):
            self.counter_hint.configure(text=icon_label("id", counter_label_text()))

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
            self._set_status("Monitoring", "run")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.append_log("Starting monitor...", "info")
        else:
            show_info(self.root, "Info", "Monitor is already running.")

    def stop_monitoring(self):
        self.controller.stop()
        self._set_status("Stopping...", "warn")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
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
                self._set_status("Idle", "idle")
                self.start_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")
            elif "Connected to IBKR" in message:
                self._set_status("Connected", "run")
        self.root.after(200, self._drain_status_queue)

    def append_log(self, message, tag="info"):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_close(self):
        if self.controller.is_running:
            if not ask_yes_no(self.root, "Quit", "Monitoring is running. Stop and quit?"):
                return
            self.controller.stop()
        self._persist_geometry()
        self.title_cleaner.stop()
        self.root.destroy()


def main():
    cfg = load_config()
    apply_appearance(bool(cfg.get("dark_mode")))
    set_ui_font_size(cfg.get("ui_font_size", 13))
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    if platform.system() == "Darwin":
        try:
            root.createcommand("tk::mac::Quit", lambda: root.event_generate("<<Quit>>"))
        except tk.TclError:
            pass
    root.title("IBKR Trade Alerts")
    CompanionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
