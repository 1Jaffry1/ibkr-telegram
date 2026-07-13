"""
IBKR Trade Alerts — companion window + settings.

Run this file to open the always-on companion:
  Start/Stop monitoring, shortcut Telegram buttons, and Settings.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox

from client import MonitorController, send_telegram_message, reload_env
from config_store import load_config, save_config, read_env_values, save_env_and_secrets


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
  {side}

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


class SettingsWindow(tk.Toplevel):
    def __init__(self, master, on_saved=None):
        super().__init__(master)
        self.title("IBKR Trade Alerts - Settings")
        self.minsize(700, 760)
        self.geometry("720x780")
        self.on_saved = on_saved
        self.app_config = load_config()
        self.load_env_file()
        self.exception_rows = []
        self.shortcut_rows = []

        button_frame = ttk.Frame(self)
        button_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        ttk.Button(button_frame, text="💾 Save", command=self.save_config).pack(side="left", padx=5)
        ttk.Button(button_frame, text="📤 Test Telegram", command=self.test_telegram).pack(side="left", padx=5)
        ttk.Button(button_frame, text="✕ Close", command=self.destroy).pack(side="right", padx=5)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        self.create_telegram_tab()
        self.create_ibkr_tab()
        self.create_assets_tab()
        self.create_percentages_tab()
        self.create_shortcuts_tab()
        self.create_messages_tab()

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
        canvas = tk.Canvas(outer, highlightthickness=0)
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
        ttk.Label(frame, text="Telegram Bot Configuration", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=2, pady=10)
        ttk.Label(
            frame,
            text="Tokens are saved to secrets.env (gitignored). Other settings stay in .env for sharing.",
            wraplength=560,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="Bot Token:").grid(row=2, column=0, sticky="w", pady=5)
        self.telegram_token = ttk.Entry(frame, width=52, show="*")
        self.telegram_token.insert(0, self.env_vars.get('TELEGRAM_BOT_TOKEN', ''))
        self.telegram_token.grid(row=2, column=1, padx=10)
        ttk.Label(frame, text="Chat/Channel ID:").grid(row=3, column=0, sticky="w", pady=5)
        self.telegram_chat_id = ttk.Entry(frame, width=52)
        self.telegram_chat_id.insert(0, self.env_vars.get('TELEGRAM_CHAT_ID', ''))
        self.telegram_chat_id.grid(row=3, column=1, padx=10)

    def create_ibkr_tab(self):
        frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(frame, text="IBKR")
        ttk.Label(frame, text="IBKR Connection Settings", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=2, pady=10)

        ttk.Label(frame, text="Host:").grid(row=1, column=0, sticky="w", pady=5)
        self.ibkr_host = ttk.Entry(frame, width=40)
        self.ibkr_host.insert(0, self.env_vars.get('IBKR_HOST', '127.0.0.1'))
        self.ibkr_host.grid(row=1, column=1, padx=10)

        ttk.Label(frame, text="Port:").grid(row=2, column=0, sticky="w", pady=5)
        self.ibkr_port = ttk.Entry(frame, width=40)
        self.ibkr_port.insert(0, self.env_vars.get('IBKR_PORT', '7496'))
        self.ibkr_port.grid(row=2, column=1, padx=10)

        ttk.Label(frame, text="Client ID:").grid(row=3, column=0, sticky="w", pady=5)
        self.ibkr_client_id = ttk.Entry(frame, width=40)
        self.ibkr_client_id.insert(0, self.env_vars.get('IBKR_CLIENT_ID', '0') or '0')
        self.ibkr_client_id.grid(row=3, column=1, padx=10)

        self.auto_stop_enabled = tk.BooleanVar(value=self._env_bool('AUTO_STOP_ENABLED', default=True))
        ttk.Checkbutton(frame, text="Enable Auto-Stop", variable=self.auto_stop_enabled, command=self._toggle_auto_stop_fields).grid(row=4, column=0, columnspan=2, sticky="w", pady=5)

        ttk.Label(frame, text="Auto-Stop Time (HH:MM):").grid(row=5, column=0, sticky="w", pady=5)
        self.stop_time = ttk.Entry(frame, width=40)
        self.stop_time.insert(0, self.env_vars.get('STOP_TIME', '16:00') or '16:00')
        self.stop_time.grid(row=5, column=1, padx=10)
        self._toggle_auto_stop_fields()

        help_box = tk.Text(frame, height=8, width=70, wrap="word")
        help_box.insert("1.0", "Gateway ports: 4001 live / 4002 paper\nTWS ports: 7496 live / 7497 paper\nUse Client ID 0 for manual TWS/Gateway/mobile orders.")
        help_box.config(state="disabled")
        help_box.grid(row=6, column=0, columnspan=2, pady=16, sticky="w")

    def _toggle_auto_stop_fields(self):
        self.stop_time.config(state="normal" if self.auto_stop_enabled.get() else "disabled")

    def create_assets_tab(self):
        frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(frame, text="Asset Types")
        ttk.Label(frame, text="Monitor These Markets", font=("Arial", 14, "bold")).pack(anchor="w", pady=10)
        ttk.Label(frame, text="Disable a type to skip Telegram alerts for that market.").pack(anchor="w", pady=(0, 12))

        self.monitor_stocks = tk.BooleanVar(value=self.app_config.get("monitor_stocks", True))
        self.monitor_options = tk.BooleanVar(value=self.app_config.get("monitor_options", True))
        self.monitor_futures = tk.BooleanVar(value=self.app_config.get("monitor_futures", True))

        ttk.Checkbutton(frame, text="Stocks", variable=self.monitor_stocks).pack(anchor="w", pady=4)
        ttk.Checkbutton(frame, text="Options (including futures options)", variable=self.monitor_options).pack(anchor="w", pady=4)
        ttk.Checkbutton(frame, text="Futures", variable=self.monitor_futures).pack(anchor="w", pady=4)

    def create_percentages_tab(self):
        frame = self._create_scrollable_tab("Percentages")
        ttk.Label(frame, text="100% Size Baselines", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=8)
        ttk.Label(
            frame,
            text="Set what 100% means for each asset type. Add symbol exceptions (e.g. GLD options = 8 contracts).",
            wraplength=640,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 12))

        defaults = self.app_config["percentages"]["defaults"]
        self.default_vars = {}
        row = 2
        for asset, title in (("stock", "Stocks default"), ("option", "Options default"), ("future", "Futures default")):
            ttk.Label(frame, text=title, font=("Arial", 10, "bold")).grid(row=row, column=0, sticky="w", pady=6)
            unit_var = tk.StringVar(value=defaults[asset]["unit"])
            value_var = tk.StringVar(value=str(defaults[asset]["value"]))
            self.default_vars[asset] = {"unit": unit_var, "value": value_var}
            unit_box = ttk.Combobox(frame, textvariable=unit_var, values=["quantity", "dollars"], width=12, state="readonly")
            unit_box.grid(row=row, column=1, padx=6)
            ttk.Entry(frame, textvariable=value_var, width=12).grid(row=row, column=2, padx=6)
            ttk.Label(frame, text="quantity = shares/contracts").grid(row=row, column=3, sticky="w")
            row += 1

        ttk.Separator(frame).grid(row=row, column=0, columnspan=4, sticky="ew", pady=12)
        row += 1
        ttk.Label(frame, text="Symbol Exceptions", font=("Arial", 12, "bold")).grid(row=row, column=0, columnspan=4, sticky="w")
        row += 1

        header = ttk.Frame(frame)
        header.grid(row=row, column=0, columnspan=4, sticky="ew", pady=4)
        for i, text in enumerate(("Symbol", "Asset", "Unit", "100% Value", "")):
            ttk.Label(header, text=text, width=12 if i < 4 else 6).grid(row=0, column=i, padx=3)
        row += 1

        self.exceptions_frame = ttk.Frame(frame)
        self.exceptions_frame.grid(row=row, column=0, columnspan=4, sticky="ew")
        row += 1

        ttk.Button(frame, text="➕ Add Exception", command=self._add_exception_row).grid(row=row, column=0, sticky="w", pady=8)

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

        ttk.Entry(row_frame, textvariable=symbol_var, width=12).grid(row=0, column=0, padx=3)
        ttk.Combobox(row_frame, textvariable=asset_var, values=["any", "stock", "option", "future"], width=10, state="readonly").grid(row=0, column=1, padx=3)
        ttk.Combobox(row_frame, textvariable=unit_var, values=["quantity", "dollars"], width=10, state="readonly").grid(row=0, column=2, padx=3)
        ttk.Entry(row_frame, textvariable=value_var, width=12).grid(row=0, column=3, padx=3)

        row_data = {"frame": row_frame, "symbol": symbol_var, "asset": asset_var, "unit": unit_var, "value": value_var}

        def remove():
            row_frame.destroy()
            self.exception_rows.remove(row_data)

        ttk.Button(row_frame, text="✕", width=3, command=remove).grid(row=0, column=4, padx=3)
        self.exception_rows.append(row_data)

    def create_shortcuts_tab(self):
        frame = self._create_scrollable_tab("Shortcuts")
        ttk.Label(frame, text="Companion Shortcut Buttons", font=("Arial", 14, "bold")).pack(anchor="w", pady=8)
        ttk.Label(frame, text="These appear on the companion window and send a Telegram message when clicked. Add or remove freely.", wraplength=640).pack(anchor="w", pady=(0, 10))

        self.shortcuts_frame = ttk.Frame(frame)
        self.shortcuts_frame.pack(fill="x")
        ttk.Button(frame, text="➕ Add Shortcut", command=self._add_shortcut_row).pack(anchor="w", pady=8)

        for item in self.app_config.get("shortcuts", []):
            self._add_shortcut_row(item)
        if not self.shortcut_rows:
            self._add_shortcut_row()

    def _add_shortcut_row(self, data=None):
        data = data or {"id": "", "label": "", "message": ""}
        row_frame = ttk.LabelFrame(self.shortcuts_frame, text="Shortcut", padding=8)
        row_frame.pack(fill="x", pady=6)

        label_var = tk.StringVar(value=data.get("label", ""))
        message_var = tk.StringVar(value=data.get("message", ""))
        id_value = data.get("id") or ""

        ttk.Label(row_frame, text="Button label:").grid(row=0, column=0, sticky="w")
        ttk.Entry(row_frame, textvariable=label_var, width=28).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(row_frame, text="Telegram message:").grid(row=1, column=0, sticky="nw", pady=4)
        msg_box = tk.Text(row_frame, height=3, width=55, wrap="word")
        msg_box.insert("1.0", data.get("message", ""))
        msg_box.grid(row=1, column=1, sticky="w", padx=6, pady=4)

        row_data = {"frame": row_frame, "id": id_value, "label": label_var, "message_box": msg_box}

        def remove():
            row_frame.destroy()
            self.shortcut_rows.remove(row_data)

        ttk.Button(row_frame, text="Remove", command=remove).grid(row=0, column=2, padx=6)
        self.shortcut_rows.append(row_data)

    def create_messages_tab(self):
        frame = self._create_scrollable_tab("Messages")
        ttk.Label(frame, text="Message Templates", font=("Arial", 14, "bold")).grid(row=0, column=0, sticky="w", pady=8)

        guide = tk.Text(frame, height=14, width=78, wrap="word")
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
            ttk.Label(frame, text=title, font=("Arial", 10, "bold")).grid(row=row, column=0, sticky="w", pady=(10, 2))
            row += 1
            box = tk.Text(frame, height=height, width=78, wrap="word")
            box.insert("1.0", self.env_vars.get(env_key) or default)
            box.grid(row=row, column=0, sticky="ew", pady=2)
            setattr(self, attr, box)
            row += 1

        ttk.Label(frame, text="Connected Message:", font=("Arial", 10, "bold")).grid(row=row, column=0, sticky="w", pady=(10, 2))
        row += 1
        self.connected_message = ttk.Entry(frame, width=78)
        self.connected_message.insert(0, self.env_vars.get('CONNECTED_MESSAGE') or '✅ Connected to IBKR. Ready for trades.')
        self.connected_message.grid(row=row, column=0, sticky="ew")
        row += 1

        ttk.Label(frame, text="Market Closed Message:", font=("Arial", 10, "bold")).grid(row=row, column=0, sticky="w", pady=(10, 2))
        row += 1
        self.closed_message = ttk.Entry(frame, width=78)
        self.closed_message.insert(0, self.env_vars.get('CLOSED_MESSAGE') or '📊 Market closed. Trade monitor stopping.')
        self.closed_message.grid(row=row, column=0, sticky="ew")

    def save_config(self):
        if not self.telegram_token.get().strip() or not self.telegram_chat_id.get().strip():
            messagebox.showerror("Error", "Telegram Bot Token and Chat ID are required!", parent=self)
            return
        if not self.connected_message.get().strip() or not self.closed_message.get().strip():
            messagebox.showerror("Error", "Connected and Market Closed messages cannot be empty.", parent=self)
            return

        if self.auto_stop_enabled.get():
            try:
                hour, minute = map(int, self.stop_time.get().strip().split(':'))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Auto-stop time must be HH:MM.", parent=self)
                return

        defaults = {}
        for asset, vars_map in self.default_vars.items():
            try:
                value = float(vars_map["value"].get())
                if value <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", f"Invalid default value for {asset}.", parent=self)
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
                messagebox.showerror("Error", f"Invalid exception value for {symbol}.", parent=self)
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
                messagebox.showerror("Error", "Each shortcut needs both a label and a message.", parent=self)
                return
            shortcuts.append({
                "id": row["id"] or label.lower().replace(" ", "_"),
                "label": label,
                "message": message,
            })
        if not shortcuts:
            messagebox.showerror("Error", "Add at least one shortcut, or keep the defaults.", parent=self)
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

        app_config = {
            "monitor_stocks": self.monitor_stocks.get(),
            "monitor_options": self.monitor_options.get(),
            "monitor_futures": self.monitor_futures.get(),
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
            messagebox.showinfo("Success", "Settings saved.\nSecrets → secrets.env\nShareable config → .env", parent=self)
            if self.on_saved:
                self.on_saved()
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save: {exc}", parent=self)

    def test_telegram(self):
        import requests
        token = self.telegram_token.get().strip()
        chat_id = self.telegram_chat_id.get().strip()
        if not token or not chat_id:
            messagebox.showerror("Error", "Enter Bot Token and Chat ID first.", parent=self)
            return
        try:
            response = requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                data={'chat_id': chat_id, 'text': '✅ Test message from IBKR Trade Alerts!', 'parse_mode': 'Markdown'},
                timeout=5,
            )
            if response.status_code == 200:
                messagebox.showinfo("Success", "Test message sent.", parent=self)
            else:
                messagebox.showerror("Error", f"Failed: {response.status_code}\n{response.text}", parent=self)
        except Exception as exc:
            messagebox.showerror("Error", f"Connection error: {exc}", parent=self)


class CompanionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("IBKR Trade Alerts")
        self.root.minsize(420, 520)
        self.root.geometry("460x560")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.controller = MonitorController(status_callback=self._queue_status)
        self._status_queue = []
        self.settings_window = None
        self.app_config = load_config()

        header = ttk.Frame(root, padding=12)
        header.pack(fill="x")
        ttk.Label(header, text="IBKR Trade Alerts", font=("Arial", 16, "bold")).pack(anchor="w")
        self.status_label = ttk.Label(header, text="Status: Idle", foreground="#555")
        self.status_label.pack(anchor="w", pady=(4, 0))

        controls = ttk.Frame(root, padding=12)
        controls.pack(fill="x")
        self.start_btn = ttk.Button(controls, text="▶ Start Monitoring", command=self.start_monitoring)
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ttk.Button(controls, text="⏹ Stop", command=self.stop_monitoring, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="⚙ Settings", command=self.open_settings).pack(side="right")

        shortcuts_wrap = ttk.LabelFrame(root, text="Shortcuts", padding=12)
        shortcuts_wrap.pack(fill="x", padx=12, pady=8)
        self.shortcuts_container = ttk.Frame(shortcuts_wrap)
        self.shortcuts_container.pack(fill="x")
        self.refresh_shortcuts()

        log_wrap = ttk.LabelFrame(root, text="Activity", padding=8)
        log_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log = tk.Text(log_wrap, height=16, wrap="word", state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_wrap, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)

        self.root.after(200, self._drain_status_queue)
        self.append_log("Companion ready. Configure Settings, then Start Monitoring.")

    def refresh_shortcuts(self):
        for child in self.shortcuts_container.winfo_children():
            child.destroy()
        self.app_config = load_config()
        shortcuts = self.app_config.get("shortcuts") or []
        if not shortcuts:
            ttk.Label(self.shortcuts_container, text="No shortcuts configured.").pack(anchor="w")
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
            messagebox.showerror("Error", "Set Telegram credentials in Settings first.")
            return
        message_id = send_telegram_message(message)
        if message_id:
            self.append_log(f"Shortcut sent: {message.splitlines()[0]}")
        else:
            self.append_log("Failed to send shortcut message.")
            messagebox.showerror("Error", "Failed to send Telegram message.")

    def open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        self.settings_window = SettingsWindow(self.root, on_saved=self.refresh_shortcuts)

    def start_monitoring(self):
        reload_env()
        if not os.getenv('TELEGRAM_BOT_TOKEN') or not os.getenv('TELEGRAM_CHAT_ID'):
            messagebox.showerror("Error", "Set Telegram credentials in Settings first.")
            return
        if self.controller.start():
            self.status_label.config(text="Status: Monitoring")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.append_log("Starting monitor...")
        else:
            messagebox.showinfo("Info", "Monitor is already running.")

    def stop_monitoring(self):
        self.controller.stop()
        self.status_label.config(text="Status: Stopping...")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.append_log("Stop requested...")

    def _queue_status(self, message):
        self._status_queue.append(message)

    def _drain_status_queue(self):
        while self._status_queue:
            message = self._status_queue.pop(0)
            self.append_log(message)
            if "Monitoring stopped" in message or "Monitor error" in message:
                self.status_label.config(text="Status: Idle")
                self.start_btn.config(state="normal")
                self.stop_btn.config(state="disabled")
            elif "Connected to IBKR" in message:
                self.status_label.config(text="Status: Connected")
        self.root.after(200, self._drain_status_queue)

    def append_log(self, message):
        self.log.config(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def on_close(self):
        if self.controller.is_running:
            if not messagebox.askyesno("Quit", "Monitoring is running. Stop and quit?"):
                return
            self.controller.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    CompanionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
