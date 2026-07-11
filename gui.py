import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from dotenv import load_dotenv, dotenv_values
import json

class IBKRAlertGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("IBKR Trade Alerts - Configuration")
        self.root.minsize(640, 720)
        self.root.geometry("640x720")
        self.root.resizable(True, True)
        
        # Load existing .env
        self.load_env_file()
        
        # Bottom buttons first so they always stay visible
        self.create_buttons()
        
        # Create notebook (tabs)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        
        # Tab 1: Telegram Settings
        self.create_telegram_tab()
        
        # Tab 2: IBKR Settings
        self.create_ibkr_tab()
        
        # Tab 3: Message Templates
        self.create_messages_tab()
    
    def _create_scrollable_tab(self, tab_title):
        """Create a tab with a vertical scrollbar for long forms."""
        outer = ttk.Frame(self.notebook)
        self.notebook.add(outer, text=tab_title)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas, padding="20")

        frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _resize_canvas(event):
            canvas.itemconfigure(canvas_window, width=event.width)

        canvas.bind("<Configure>", _resize_canvas)

        def _on_mousewheel(event):
            if event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")
            elif event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")

        for widget in (canvas, frame, outer):
            widget.bind("<Enter>", lambda e, c=canvas: self._bind_mousewheel(c))
            widget.bind("<Leave>", lambda e: self._unbind_mousewheel())

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        return frame

    def _bind_mousewheel(self, canvas):
        self.root.bind_all("<MouseWheel>", lambda e: self._scroll_canvas(canvas, e))
        self.root.bind_all("<Button-4>", lambda e: self._scroll_canvas(canvas, e))
        self.root.bind_all("<Button-5>", lambda e: self._scroll_canvas(canvas, e))

    def _unbind_mousewheel(self):
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")

    def _scroll_canvas(self, canvas, event):
        if event.delta:
            canvas.yview_scroll(int(-event.delta / 120), "units")
        elif event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")
    
    def load_env_file(self):
        """Load .env file if it exists"""
        self.env_path = ".env"
        if os.path.exists(self.env_path):
            self.env_vars = dotenv_values(self.env_path)
        else:
            self.env_vars = {}
    
    def create_telegram_tab(self):
        """Tab for Telegram configuration"""
        frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(frame, text="Telegram Settings")
        
        # Title
        title = ttk.Label(frame, text="Telegram Bot Configuration", font=("Arial", 14, "bold"))
        title.grid(row=0, column=0, columnspan=2, pady=10)
        
        # Bot Token
        ttk.Label(frame, text="Bot Token:").grid(row=1, column=0, sticky="w", pady=5)
        self.telegram_token = ttk.Entry(frame, width=50, show="*")
        self.telegram_token.insert(0, self.env_vars.get('TELEGRAM_BOT_TOKEN', ''))
        self.telegram_token.grid(row=1, column=1, padx=10)
        
        # Chat ID
        ttk.Label(frame, text="Chat/Channel ID:").grid(row=2, column=0, sticky="w", pady=5)
        self.telegram_chat_id = ttk.Entry(frame, width=50)
        self.telegram_chat_id.insert(0, self.env_vars.get('TELEGRAM_CHAT_ID', ''))
        self.telegram_chat_id.grid(row=2, column=1, padx=10)
        
        # Instructions
        instructions = ttk.Frame(frame)
        instructions.grid(row=3, column=0, columnspan=2, pady=20)
        
        instr_text = tk.Text(instructions, height=10, width=65, wrap="word")
        instr_text.insert("1.0", """HOW TO GET TELEGRAM CREDENTIALS:

1. Open Telegram and search for @BotFather
2. Send /newbot and follow the prompts
3. Copy the Bot Token here ↑

4. Send any message to your bot
5. Open this URL in browser (replace TOKEN):
   https://api.telegram.org/botTOKEN/getUpdates
6. Find "chat": { "id": XXXXX }
7. Copy that ID here ↑

For channels, add your bot as admin first.
Channel IDs start with -100""")
        instr_text.config(state="disabled")
        instr_text.pack()
    
    def create_ibkr_tab(self):
        """Tab for IBKR configuration"""
        frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(frame, text="IBKR Settings")
        
        # Title
        title = ttk.Label(frame, text="IBKR Connection Settings", font=("Arial", 14, "bold"))
        title.grid(row=0, column=0, columnspan=2, pady=10)
        
        # Host
        ttk.Label(frame, text="Host:").grid(row=1, column=0, sticky="w", pady=5)
        self.ibkr_host = ttk.Entry(frame, width=50)
        self.ibkr_host.insert(0, self.env_vars.get('IBKR_HOST', '127.0.0.1'))
        self.ibkr_host.grid(row=1, column=1, padx=10)
        
        # Port
        ttk.Label(frame, text="Port:").grid(row=2, column=0, sticky="w", pady=5)
        self.ibkr_port = ttk.Entry(frame, width=50)
        self.ibkr_port.insert(0, self.env_vars.get('IBKR_PORT', '7496'))
        self.ibkr_port.grid(row=2, column=1, padx=10)
        
        # Client ID
        ttk.Label(frame, text="Client ID:").grid(row=3, column=0, sticky="w", pady=5)
        self.ibkr_client_id = ttk.Entry(frame, width=50)
        self.ibkr_client_id.insert(0, self.env_vars.get('IBKR_CLIENT_ID', '0') or '0')
        self.ibkr_client_id.grid(row=3, column=1, padx=10)
        
        # Auto-Stop
        self.auto_stop_enabled = tk.BooleanVar(
            value=self._env_bool('AUTO_STOP_ENABLED', default=True)
        )
        auto_stop_frame = ttk.Frame(frame)
        auto_stop_frame.grid(row=4, column=0, columnspan=2, sticky="w", pady=5)
        self.auto_stop_check = ttk.Checkbutton(
            auto_stop_frame,
            text="Enable Auto-Stop",
            variable=self.auto_stop_enabled,
            command=self._toggle_auto_stop_fields
        )
        self.auto_stop_check.pack(side="left")
        
        ttk.Label(frame, text="Auto-Stop Time (HH:MM):").grid(row=5, column=0, sticky="w", pady=5)
        self.stop_time = ttk.Entry(frame, width=50)
        self.stop_time.insert(0, self.env_vars.get('STOP_TIME', '16:00') or '16:00')
        self.stop_time.grid(row=5, column=1, padx=10)
        self._toggle_auto_stop_fields()
        
        # Instructions
        instructions = ttk.Frame(frame)
        instructions.grid(row=6, column=0, columnspan=2, pady=20)
        
        instr_text = tk.Text(instructions, height=8, width=65, wrap="word")
        instr_text.insert("1.0", """IBKR CONNECTION SETTINGS:

Works with IB Gateway (recommended) or Trader Workstation (TWS).
Both use the same socket API — only host/port differ.

Host: Leave as 127.0.0.1 (localhost)
Ports:
  IB Gateway — 4001 live, 4002 paper
  TWS        — 7496 live, 7497 paper
  (Check API settings if you changed the default port)

Client ID: Use 0 to detect orders placed via mobile, TWS, etc.
Auto-Stop: Turn off to keep listening after market close
Auto-Stop Time: When to stop listening (e.g., 16:00 = 4 PM)

API settings (Gateway or TWS):
- Enable ActiveX and Socket Clients
- Optional: set Master API Client ID to 0

Make sure IB Gateway or TWS is running before starting alerts!""")
        instr_text.config(state="disabled")
        instr_text.pack()
    
    def _env_bool(self, key, default=False):
        value = self.env_vars.get(key)
        if value is None:
            return default
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on')
    
    def _toggle_auto_stop_fields(self):
        state = "normal" if self.auto_stop_enabled.get() else "disabled"
        self.stop_time.config(state=state)
    
    def create_messages_tab(self):
        """Tab for message templates"""
        frame = self._create_scrollable_tab("Message Templates")
        
        # Title
        title = ttk.Label(frame, text="Customize Trade Alert Messages", font=("Arial", 14, "bold"))
        title.grid(row=0, column=0, columnspan=2, pady=10)
        
        # Order Submitted Message
        ttk.Label(frame, text="Order Submitted (Stock):", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="nw", pady=5)

        self.order_message = tk.Text(frame, height=6, width=65, wrap="word")
        default_order_message = """📝 *ORDER SUBMITTED*

*Symbol:* `{symbol}`
*Exchange:* `{exchange}`
*Action:* `{action}`
*Quantity:* `{quantity}`
*Type:* `{order_type}`
*Price:* `{limit_price}`
*Status:* `{status}`"""

        self.order_message.insert("1.0", self.env_vars.get('ORDER_MESSAGE', default_order_message))
        self.order_message.grid(row=2, column=0, columnspan=2, padx=10, pady=5)

        ttk.Label(frame, text="Order Submitted (Option):", font=("Arial", 10, "bold")).grid(row=3, column=0, sticky="nw", pady=5)

        self.order_option_message = tk.Text(frame, height=7, width=65, wrap="word")
        default_order_option_message = """📝 *OPTION ORDER SUBMITTED*

*Underlying:* `{symbol}`
*Contract:* `{contract_description}`
*Action:* `{action}`
*Contracts:* `{quantity}`
*Type:* `{order_type}`
*Price:* `{limit_price}`
*Status:* `{status}`"""

        self.order_option_message.insert("1.0", self.env_vars.get('ORDER_OPTION_MESSAGE', default_order_option_message))
        self.order_option_message.grid(row=4, column=0, columnspan=2, padx=10, pady=5)

        # Fill Message
        ttk.Label(frame, text="Order Filled (Stock):", font=("Arial", 10, "bold")).grid(row=5, column=0, sticky="nw", pady=5)
        
        self.trade_message = tk.Text(frame, height=6, width=65, wrap="word")
        default_message = """✅ *ORDER FILLED*

*Symbol:* `{symbol}`
*Exchange:* `{exchange}`
*Action:* `{side}`
*Quantity:* `{quantity}`
*Price:* `${price}`
*Commission:* `${commission}`
*Time:* `{time}`
*Account:* `{account}`"""
        
        self.trade_message.insert("1.0", self.env_vars.get('TRADE_MESSAGE', default_message))
        self.trade_message.grid(row=6, column=0, columnspan=2, padx=10, pady=5)
        
        # Option Fill Message
        ttk.Label(frame, text="Order Filled (Option):", font=("Arial", 10, "bold")).grid(row=7, column=0, sticky="nw", pady=5)
        
        self.option_message = tk.Text(frame, height=7, width=65, wrap="word")
        default_option_message = """✅ *OPTION ORDER FILLED*

*Underlying:* `{symbol}`
*Contract:* `{contract_description}`
*Type:* `{option_type}`
*Strike:* `${strike}`
*Expiry:* `{expiry}`
*Action:* `{side}`
*Contracts:* `{quantity}`
*Price:* `${price}`
*Commission:* `${commission}`
*Time:* `{time}`
*Account:* `{account}`"""
        
        self.option_message.insert("1.0", self.env_vars.get('OPTION_MESSAGE', default_option_message))
        self.option_message.grid(row=8, column=0, columnspan=2, padx=10, pady=5)
        
        # Connection Message
        ttk.Label(frame, text="Connected Message:", font=("Arial", 10, "bold")).grid(row=9, column=0, sticky="nw", pady=5)
        
        self.connected_message = ttk.Entry(frame, width=65)
        self.connected_message.insert(0, self.env_vars.get('CONNECTED_MESSAGE') or '✅ Connected to IBKR. Ready for trades.')
        self.connected_message.grid(row=10, column=0, columnspan=2, padx=10, pady=5)
        
        # Market Closed Message
        ttk.Label(frame, text="Market Closed Message:", font=("Arial", 10, "bold")).grid(row=11, column=0, sticky="nw", pady=5)
        
        self.closed_message = ttk.Entry(frame, width=65)
        self.closed_message.insert(0, self.env_vars.get('CLOSED_MESSAGE') or '📊 Market closed. Trade monitor stopping.')
        self.closed_message.grid(row=12, column=0, columnspan=2, padx=10, pady=5)
        
        # Help text
        help_text = ttk.Label(
            frame,
            text=(
                "Submission: {symbol}, {action}, {quantity}, {order_type}, {limit_price}, {status}\n"
                "Fill (silent reply): {side}, {price}, {commission}, {time}, {account}\n"
                "Options also: {contract_description}, {option_type}, {strike}, {expiry}"
            ),
            font=("Arial", 8, "italic"),
            justify="left"
        )
        help_text.grid(row=13, column=0, columnspan=2, pady=10, sticky="w")
    
    def create_buttons(self):
        """Create save and test buttons"""
        button_frame = ttk.Frame(self.root)
        button_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        
        save_btn = ttk.Button(button_frame, text="💾 Save Configuration", command=self.save_config)
        save_btn.pack(side="left", padx=5)
        
        test_btn = ttk.Button(button_frame, text="📤 Test Telegram", command=self.test_telegram)
        test_btn.pack(side="left", padx=5)
        
        reset_btn = ttk.Button(button_frame, text="🔄 Reset to Defaults", command=self.reset_defaults)
        reset_btn.pack(side="left", padx=5)
        
        quit_btn = ttk.Button(button_frame, text="✕ Exit", command=self.root.quit)
        quit_btn.pack(side="right", padx=5)
    
    def save_config(self):
        """Save configuration to .env file"""
        config = {
            'TELEGRAM_BOT_TOKEN': self.telegram_token.get(),
            'TELEGRAM_CHAT_ID': self.telegram_chat_id.get(),
            'IBKR_HOST': self.ibkr_host.get(),
            'IBKR_PORT': self.ibkr_port.get(),
            'IBKR_CLIENT_ID': self.ibkr_client_id.get(),
            'AUTO_STOP_ENABLED': 'true' if self.auto_stop_enabled.get() else 'false',
            'STOP_TIME': self.stop_time.get(),
            'ORDER_MESSAGE': self.order_message.get("1.0", "end-1c"),
            'ORDER_OPTION_MESSAGE': self.order_option_message.get("1.0", "end-1c"),
            'TRADE_MESSAGE': self.trade_message.get("1.0", "end-1c"),
            'OPTION_MESSAGE': self.option_message.get("1.0", "end-1c"),
            'CONNECTED_MESSAGE': self.connected_message.get(),
            'CLOSED_MESSAGE': self.closed_message.get(),
        }
        
        # Validate
        if not config['TELEGRAM_BOT_TOKEN'] or not config['TELEGRAM_CHAT_ID']:
            messagebox.showerror("Error", "Telegram Bot Token and Chat ID are required!")
            return

        if not config['CONNECTED_MESSAGE'].strip() or not config['CLOSED_MESSAGE'].strip():
            messagebox.showerror("Error", "Connected and Market Closed messages cannot be empty.")
            return
        
        if self.auto_stop_enabled.get():
            stop_time = config['STOP_TIME'].strip()
            try:
                hour, minute = map(int, stop_time.split(':'))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except ValueError:
                messagebox.showerror("Error", "Auto-stop time must be in HH:MM format (e.g., 16:00).")
                return
        
        # Write to .env
        try:
            with open(self.env_path, 'w') as f:
                for key, value in config.items():
                    # Escape special characters in values
                    value = value.replace('"', '\\"')
                    f.write(f'{key}="{value}"\n')
            
            messagebox.showinfo("Success", "✅ Configuration saved successfully!")
            self.load_env_file()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {str(e)}")
    
    def test_telegram(self):
        """Send a test message to Telegram"""
        import requests
        
        token = self.telegram_token.get()
        chat_id = self.telegram_chat_id.get()
        
        if not token or not chat_id:
            messagebox.showerror("Error", "Please enter Bot Token and Chat ID first!")
            return
        
        try:
            url = f'https://api.telegram.org/bot{token}/sendMessage'
            data = {
                'chat_id': chat_id,
                'text': '✅ Test message from IBKR Trade Alerts!\n\nConfiguration is working!',
                'parse_mode': 'Markdown'
            }
            response = requests.post(url, data=data, timeout=5)
            
            if response.status_code == 200:
                messagebox.showinfo("Success", "✅ Test message sent!\nCheck your Telegram.")
            else:
                messagebox.showerror("Error", f"Failed to send. Status: {response.status_code}\n\nCheck your Bot Token and Chat ID.")
        except Exception as e:
            messagebox.showerror("Error", f"Connection error: {str(e)}")
    
    def reset_defaults(self):
        """Reset to default values"""
        if messagebox.askyesno("Confirm", "Reset all settings to defaults?"):
            self.telegram_token.delete(0, "end")
            self.telegram_chat_id.delete(0, "end")
            self.ibkr_host.delete(0, "end")
            self.ibkr_host.insert(0, '127.0.0.1')
            self.ibkr_port.delete(0, "end")
            self.ibkr_port.insert(0, '7496')
            self.ibkr_client_id.delete(0, "end")
            self.ibkr_client_id.insert(0, '0')
            self.auto_stop_enabled.set(True)
            self._toggle_auto_stop_fields()
            self.stop_time.delete(0, "end")
            self.stop_time.insert(0, '16:00')
            
            default_order_message = """📝 *ORDER SUBMITTED*

*Symbol:* `{symbol}`
*Exchange:* `{exchange}`
*Action:* `{action}`
*Quantity:* `{quantity}`
*Type:* `{order_type}`
*Price:* `{limit_price}`
*Status:* `{status}`"""

            self.order_message.delete("1.0", "end")
            self.order_message.insert("1.0", default_order_message)

            default_order_option_message = """📝 *OPTION ORDER SUBMITTED*

*Underlying:* `{symbol}`
*Contract:* `{contract_description}`
*Action:* `{action}`
*Contracts:* `{quantity}`
*Type:* `{order_type}`
*Price:* `{limit_price}`
*Status:* `{status}`"""

            self.order_option_message.delete("1.0", "end")
            self.order_option_message.insert("1.0", default_order_option_message)
            
            default_message = """✅ *ORDER FILLED*

*Symbol:* `{symbol}`
*Exchange:* `{exchange}`
*Action:* `{side}`
*Quantity:* `{quantity}`
*Price:* `${price}`
*Commission:* `${commission}`
*Time:* `{time}`
*Account:* `{account}`"""
            
            self.trade_message.delete("1.0", "end")
            self.trade_message.insert("1.0", default_message)
            
            default_option_message = """✅ *OPTION ORDER FILLED*

*Underlying:* `{symbol}`
*Contract:* `{contract_description}`
*Type:* `{option_type}`
*Strike:* `${strike}`
*Expiry:* `{expiry}`
*Exchange:* `{exchange}`
*Action:* `{side}`
*Contracts:* `{quantity}`
*Price:* `${price}`
*Commission:* `${commission}`
*Time:* `{time}`
*Account:* `{account}`"""
            
            self.option_message.delete("1.0", "end")
            self.option_message.insert("1.0", default_option_message)
            
            self.connected_message.delete(0, "end")
            self.connected_message.insert(0, '✅ Connected to IBKR. Ready for trades.')
            
            self.closed_message.delete(0, "end")
            self.closed_message.insert(0, '📊 Market closed. Trade monitor stopping.')

if __name__ == "__main__":
    root = tk.Tk()
    app = IBKRAlertGUI(root)
    root.mainloop()