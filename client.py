import os
import sys
import threading
import time as time_module
from datetime import datetime, time
from ibapi.client import EClient
from ibapi.common import UNSET_DOUBLE
from ibapi.wrapper import EWrapper
import requests

from config_store import (
    calculate_percentage,
    format_percentage_label,
    is_asset_enabled,
    load_config,
    load_env_files,
)
from summary_store import current_cnt_emoji
load_env_files()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

OPTION_SEC_TYPES = {'OPT', 'FOP', 'IOPT'}
FUTURE_SEC_TYPES = {'FUT', 'CONTFUT'}
SUBMISSION_STATUSES = {'Submitted', 'PreSubmitted', 'PendingSubmit'}

def getenv_or_default(key, default):
    value = os.getenv(key)
    if value is None or not str(value).strip():
        return default
    return value


def reload_env():
    load_env_files(override=True)
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    global CONNECTED_MESSAGE, CLOSED_MESSAGE
    global ORDER_MESSAGE_TEMPLATE, ORDER_OPTION_MESSAGE_TEMPLATE, ORDER_FUTURE_MESSAGE_TEMPLATE
    global TRADE_MESSAGE_TEMPLATE, OPTION_MESSAGE_TEMPLATE, FUTURE_MESSAGE_TEMPLATE
    global AUTO_STOP_ENABLED, STOP_TIME

    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    CONNECTED_MESSAGE = getenv_or_default('CONNECTED_MESSAGE', '✅ Connected to IBKR. Ready for trades.')
    CLOSED_MESSAGE = getenv_or_default('CLOSED_MESSAGE', '📊 Market closed. Trade monitor stopping.')
    ORDER_MESSAGE_TEMPLATE = getenv_or_default('ORDER_MESSAGE', DEFAULT_ORDER_MESSAGE)
    ORDER_OPTION_MESSAGE_TEMPLATE = getenv_or_default('ORDER_OPTION_MESSAGE', DEFAULT_ORDER_OPTION_MESSAGE)
    ORDER_FUTURE_MESSAGE_TEMPLATE = getenv_or_default('ORDER_FUTURE_MESSAGE', DEFAULT_ORDER_FUTURE_MESSAGE)
    TRADE_MESSAGE_TEMPLATE = getenv_or_default('TRADE_MESSAGE', DEFAULT_TRADE_MESSAGE)
    OPTION_MESSAGE_TEMPLATE = getenv_or_default('OPTION_MESSAGE', DEFAULT_OPTION_MESSAGE)
    FUTURE_MESSAGE_TEMPLATE = getenv_or_default('FUTURE_MESSAGE', DEFAULT_FUTURE_MESSAGE)
    AUTO_STOP_ENABLED = parse_bool(os.getenv('AUTO_STOP_ENABLED'), default=True)

    stop_time_str = os.getenv('STOP_TIME', '16:00')
    try:
        stop_hour, stop_minute = map(int, stop_time_str.split(':'))
        STOP_TIME = time(stop_hour, stop_minute)
    except Exception:
        STOP_TIME = time(16, 0)

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

CONNECTED_MESSAGE = getenv_or_default('CONNECTED_MESSAGE', '✅ Connected to IBKR. Ready for trades.')
CLOSED_MESSAGE = getenv_or_default('CLOSED_MESSAGE', '📊 Market closed. Trade monitor stopping.')
ORDER_MESSAGE_TEMPLATE = getenv_or_default('ORDER_MESSAGE', DEFAULT_ORDER_MESSAGE)
ORDER_OPTION_MESSAGE_TEMPLATE = getenv_or_default('ORDER_OPTION_MESSAGE', DEFAULT_ORDER_OPTION_MESSAGE)
ORDER_FUTURE_MESSAGE_TEMPLATE = getenv_or_default('ORDER_FUTURE_MESSAGE', DEFAULT_ORDER_FUTURE_MESSAGE)
TRADE_MESSAGE_TEMPLATE = getenv_or_default('TRADE_MESSAGE', DEFAULT_TRADE_MESSAGE)
OPTION_MESSAGE_TEMPLATE = getenv_or_default('OPTION_MESSAGE', DEFAULT_OPTION_MESSAGE)
FUTURE_MESSAGE_TEMPLATE = getenv_or_default('FUTURE_MESSAGE', DEFAULT_FUTURE_MESSAGE)

def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

stop_time_str = os.getenv('STOP_TIME', '16:00')
try:
    stop_hour, stop_minute = map(int, stop_time_str.split(':'))
    STOP_TIME = time(stop_hour, stop_minute)
except Exception:
    STOP_TIME = time(16, 0)

AUTO_STOP_ENABLED = parse_bool(os.getenv('AUTO_STOP_ENABLED'), default=True)

def should_auto_stop():
    return AUTO_STOP_ENABLED and datetime.now().time() >= STOP_TIME

def is_option_contract(contract):
    return contract.secType in OPTION_SEC_TYPES

def is_future_contract(contract):
    return contract.secType in FUTURE_SEC_TYPES

def format_expiry(expiry):
    if not expiry:
        return ''
    expiry = str(expiry).strip()
    if len(expiry) >= 8:
        return f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}"
    if len(expiry) == 6:
        return f"{expiry[:4]}-{expiry[4:6]}"
    return expiry

def format_option_type(right):
    return {'C': 'Call', 'P': 'Put'}.get(right, right or 'N/A')

def format_side(side):
    """Map IBKR execution codes to readable labels."""
    return {
        'BOT': 'BOUGHT',
        'SLD': 'SOLD',
        'BUY': 'BUY',
        'SELL': 'SELL',
        'SSHORT': 'SHORT',
    }.get(side, side or '')

def format_limit_price(order):
    if order.orderType in ('MKT', 'MIDPRICE') or order.lmtPrice in (UNSET_DOUBLE, None):
        return 'Market'
    return f"${order.lmtPrice:g}"

def build_contract_description(contract):
    if is_option_contract(contract):
        return (
            f"{contract.symbol} {format_expiry(contract.lastTradeDateOrContractMonth)} "
            f"${contract.strike:g} {format_option_type(contract.right)}"
        )
    if is_future_contract(contract):
        if contract.localSymbol:
            return contract.localSymbol
        expiry = format_expiry(contract.lastTradeDateOrContractMonth)
        return f"{contract.symbol} {expiry}".strip()
    return contract.symbol

def select_message_template(contract, stock_template, option_template, future_template):
    if is_option_contract(contract):
        return option_template
    if is_future_contract(contract):
        return future_template
    return stock_template

def build_contract_context(contract, quantity=0, price=0, app_config=None):
    is_option = is_option_contract(contract)
    is_future = is_future_contract(contract)
    expiry = ''
    if is_option or is_future:
        expiry = format_expiry(contract.lastTradeDateOrContractMonth)

    config = app_config if app_config is not None else load_config()
    quantity = float(quantity or 0)
    pct = calculate_percentage(config, contract, quantity, price)
    if quantity == int(quantity):
        quantity_display = int(quantity)
    else:
        quantity_display = quantity

    return {
        'symbol': contract.symbol,
        'exchange': contract.exchange or contract.primaryExchange or '',
        'contract_description': build_contract_description(contract),
        'option_type': format_option_type(contract.right) if is_option else '',
        'strike': contract.strike if is_option else '',
        'expiry': expiry,
        'local_symbol': contract.localSymbol or contract.symbol,
        'multiplier': contract.multiplier or '',
        'trading_class': contract.tradingClass or '',
        'sec_type': contract.secType,
        'quantity': quantity_display,
        'percentage': format_percentage_label(pct),
        'percentage_raw': pct if pct is not None else '',
        # Number-emoji trade ID (e.g. 1️⃣4️⃣). Empty until a mapped shortcut increments it.
        'cnt': current_cnt_emoji(),
    }

def build_order_context(contract, order, status='', app_config=None):
    price = 0
    if order.orderType not in ('MKT', 'MIDPRICE') and order.lmtPrice not in (UNSET_DOUBLE, None):
        price = order.lmtPrice
    context = build_contract_context(contract, order.totalQuantity, price, app_config=app_config)
    context.update({
        'action': format_side(order.action),
        'order_type': order.orderType,
        'limit_price': format_limit_price(order),
        'status': status,
        'price': price,
    })
    return context

def build_trade_context(contract, execution, commission, app_config=None, quantity=None):
    # Prefer full filled size (cumQty / order total), not just the last partial lot.
    if quantity is None:
        quantity = execution.cumQty or execution.shares
    quantity = float(quantity or 0)
    context = build_contract_context(contract, quantity, execution.price, app_config=app_config)
    context.update({
        'side': format_side(execution.side),
        'price': execution.price,
        'commission': commission,
        'time': execution.time,
        'account': execution.acctNumber,
    })
    return context

def format_order_message(contract, order, status='', app_config=None):
    context = build_order_context(contract, order, status, app_config=app_config)
    template = select_message_template(
        contract,
        ORDER_MESSAGE_TEMPLATE,
        ORDER_OPTION_MESSAGE_TEMPLATE,
        ORDER_FUTURE_MESSAGE_TEMPLATE,
    )
    return template.format(**context)

def format_trade_message(contract, execution, commission, app_config=None, quantity=None):
    context = build_trade_context(
        contract, execution, commission, app_config=app_config, quantity=quantity
    )
    template = select_message_template(
        contract,
        TRADE_MESSAGE_TEMPLATE,
        OPTION_MESSAGE_TEMPLATE,
        FUTURE_MESSAGE_TEMPLATE,
    )
    return template.format(**context)

def send_telegram_message(message, reply_to=None, silent=False):
    """Send message via Telegram. Returns message_id on success."""
    if not message or not str(message).strip():
        print("⚠️  Skipping empty Telegram message")
        return None

    token = os.getenv('TELEGRAM_BOT_TOKEN') or TELEGRAM_BOT_TOKEN
    chat_id = os.getenv('TELEGRAM_CHAT_ID') or TELEGRAM_CHAT_ID
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
    }
    if reply_to is not None:
        data['reply_to_message_id'] = reply_to
    if silent:
        data['disable_notification'] = True

    try:
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            return response.json().get('result', {}).get('message_id')
        print(f"❌ Telegram API error {response.status_code}: {response.text}")
        if response.status_code == 400 and 'parse' in response.text.lower():
            fallback = {k: v for k, v in data.items() if k != 'parse_mode'}
            retry = requests.post(url, data=fallback, timeout=10)
            if retry.status_code == 200:
                return retry.json().get('result', {}).get('message_id')
            print(f"❌ Telegram retry error {retry.status_code}: {retry.text}")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")
    return None

class TradeMonitor(EWrapper, EClient):
    def __init__(self, client_id, status_callback=None, allow_exit=True):
        EClient.__init__(self, self)
        self.client_id = client_id
        self.status_callback = status_callback
        self.allow_exit = allow_exit
        self.stop_requested = False
        self.nextOrderId = None
        self.orders_by_perm_id = {}
        self.orders_by_order_id = {}
        self.order_status_by_perm_id = {}
        self.submission_message_ids = {}
        self.last_execution_by_perm_id = {}
        self.notified_submissions = set()
        self.notified_fills = set()
        self.pending_executions = {}
        self.app_config = load_config()

    def _emit(self, message):
        print(message)
        if self.status_callback:
            try:
                self.status_callback(message)
            except Exception:
                pass

    def request_stop(self):
        self.stop_requested = True
        try:
            self.disconnect()
        except Exception:
            pass

    def reload_runtime_config(self):
        reload_env()
        self.app_config = load_config()

    def nextValidId(self, orderId):
        self.nextOrderId = orderId
        self.reload_runtime_config()
        self._emit(CONNECTED_MESSAGE)
        send_telegram_message(CONNECTED_MESSAGE)
        self._subscribe_to_orders()

    def _subscribe_to_orders(self):
        if self.client_id == 0:
            self._emit("🔗 Binding manual orders (client ID 0)...")
            self.reqAutoOpenOrders(True)
            self.reqOpenOrders()
        else:
            self._emit("⚠️  Client ID is not 0 — manual orders may not be detected.")
            self.reqAllOpenOrders()

    def _should_skip_contract(self, contract):
        self.app_config = load_config()
        if not is_asset_enabled(self.app_config, contract):
            label = build_contract_description(contract)
            self._emit(f"⏭️  Skipping {label} ({contract.secType}) — asset type disabled")
            return True
        return False

    def openOrder(self, orderId, contract, order, orderState):
        if self.stop_requested:
            return
        if should_auto_stop():
            self._handle_auto_stop()
            return
        if self._should_skip_contract(contract):
            return

        perm_id = order.permId or self._perm_id_for_order(orderId)
        state_status = (orderState.status or '').strip()

        self.orders_by_perm_id[perm_id] = {
            'contract': contract,
            'order': order,
            'orderId': orderId,
        }
        self.orders_by_order_id[orderId] = perm_id

        if state_status:
            self.order_status_by_perm_id[perm_id] = {
                'status': state_status,
                'filled': 0,
                'remaining': order.totalQuantity,
                'avgFillPrice': 0,
                'orderId': orderId,
            }

        self._emit(
            f"📋 openOrder: {build_contract_description(contract)} "
            f"status={state_status or 'n/a'} permId={perm_id}"
        )
        self._try_notify_submission(perm_id, state_status)

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId,
                    parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        if self.stop_requested:
            return
        if should_auto_stop():
            self._handle_auto_stop()
            return

        self.order_status_by_perm_id[permId] = {
            'status': status,
            'filled': filled,
            'remaining': remaining,
            'avgFillPrice': avgFillPrice,
            'orderId': orderId,
        }
        self.orders_by_order_id[orderId] = permId

        order_info = self.orders_by_perm_id.get(permId)
        if order_info and self._should_skip_contract(order_info['contract']):
            return

        self._emit(
            f"📊 orderStatus: permId={permId} status={status} "
            f"filled={filled} remaining={remaining}"
        )

        if status in SUBMISSION_STATUSES:
            self._try_notify_submission(permId, status)
        elif status == 'Filled':
            self._try_notify_fill(permId)
        elif remaining == 0 and filled > 0:
            self._try_notify_fill(permId)

    def execDetails(self, reqId, contract, execution):
        if self.stop_requested:
            return
        if should_auto_stop():
            self._handle_auto_stop()
            return
        if self._should_skip_contract(contract):
            return

        self.pending_executions[execution.execId] = (contract, execution)
        self.last_execution_by_perm_id[execution.permId] = (contract, execution)
        self._emit(
            f"💱 execDetails: {build_contract_description(contract)} "
            f"qty={execution.shares} price={execution.price}"
        )

    def commissionReport(self, commissionReport):
        pending = self.pending_executions.pop(commissionReport.execId, None)
        if not pending:
            return

        contract, execution = pending
        if self._should_skip_contract(contract):
            return
        self.last_execution_by_perm_id[execution.permId] = (
            contract,
            execution,
            commissionReport.commission,
        )
        self._try_notify_fill(execution.permId)

    def execDetailsEnd(self, reqId):
        for exec_id, (contract, execution) in list(self.pending_executions.items()):
            if self._should_skip_contract(contract):
                del self.pending_executions[exec_id]
                continue
            self.last_execution_by_perm_id[execution.permId] = (contract, execution, 0)
            self._try_notify_fill(execution.permId)
            del self.pending_executions[exec_id]

    def _perm_id_for_order(self, order_id):
        return self.orders_by_order_id.get(order_id, order_id)

    def _handle_auto_stop(self):
        self._emit(f"⏰ {CLOSED_MESSAGE}")
        send_telegram_message(CLOSED_MESSAGE)
        self.stop_requested = True
        try:
            self.disconnect()
        except Exception:
            pass
        if self.allow_exit:
            sys.exit(0)

    def _try_notify_submission(self, perm_id, status=''):
        if perm_id in self.notified_submissions:
            return

        self.app_config = load_config()
        if not self.app_config.get("notify_order_submitted", True):
            # Mark as handled so fill alerts do not try to send a submission first.
            self.notified_submissions.add(perm_id)
            return

        order_info = self.orders_by_perm_id.get(perm_id)
        if not order_info:
            return

        status_info = self.order_status_by_perm_id.get(perm_id, {})
        current_status = status or status_info.get('status', '')
        if current_status in ('Cancelled', 'Inactive', 'ApiCancelled'):
            return

        contract = order_info['contract']
        order = order_info['order']
        message = format_order_message(
            contract, order,
            'Submitted' if current_status == 'Filled' else (current_status or 'Submitted'),
            app_config=self.app_config,
        )
        label = build_contract_description(contract)
        message_id = send_telegram_message(message)

        if message_id:
            self.notified_submissions.add(perm_id)
            self.submission_message_ids[perm_id] = message_id
            self._emit(f"📤 Order submitted alert sent for {label}")
        else:
            self._emit(f"❌ Failed to send order submitted alert for {label}")

    def _try_notify_fill(self, perm_id):
        if perm_id in self.notified_fills:
            return

        execution_info = self.last_execution_by_perm_id.get(perm_id)
        if not execution_info:
            return

        status_info = self.order_status_by_perm_id.get(perm_id)
        if status_info:
            is_complete = (
                status_info['status'] == 'Filled'
                or (status_info.get('remaining', 1) == 0 and status_info.get('filled', 0) > 0)
            )
            if not is_complete:
                return

        if len(execution_info) == 3:
            contract, execution, commission = execution_info
        else:
            contract, execution = execution_info
            commission = 0

        if perm_id not in self.notified_submissions:
            order_info = self.orders_by_perm_id.get(perm_id)
            if order_info:
                self._try_notify_submission(perm_id)

        # Use full order size for %, not the last partial fill lot.
        order_info = self.orders_by_perm_id.get(perm_id)
        fill_qty = float(getattr(execution, 'cumQty', 0) or 0) or float(execution.shares or 0)
        if status_info and status_info.get('filled'):
            fill_qty = max(fill_qty, float(status_info['filled']))
        if order_info and status_info and (
            status_info.get('status') == 'Filled'
            or float(status_info.get('remaining', 1) or 1) == 0
        ):
            fill_qty = max(fill_qty, float(order_info['order'].totalQuantity or 0))

        trade_msg = format_trade_message(
            contract, execution, commission,
            app_config=self.app_config,
            quantity=fill_qty,
        )
        label = build_contract_description(contract)
        reply_to = self.submission_message_ids.get(perm_id)
        # Silent only when replying under a prior submission alert.
        message_id = send_telegram_message(trade_msg, reply_to=reply_to, silent=bool(reply_to))

        if message_id:
            self.notified_fills.add(perm_id)
            self._emit(f"✅ Fill alert sent for {label}")
        else:
            self._emit(f"❌ Failed to send fill alert for {label}")

    def error(self, reqId, errorCode, errorString):
        if errorCode not in (1100, 2104, 2106, 2158):
            self._emit(f"❌ Error {errorCode}: {errorString}")

    def connectionClosed(self):
        if self.stop_requested:
            self._emit("🛑 Monitoring stopped")
            return
        self._emit("⚠️  Connection closed. Reconnecting...")
        time_module.sleep(5)
        if self.stop_requested:
            return
        self.connect(
            os.getenv('IBKR_HOST', '127.0.0.1'),
            int(os.getenv('IBKR_PORT', 7496)),
            int(os.getenv('IBKR_CLIENT_ID', '0'))
        )


class MonitorController:
    """Start/stop TradeMonitor from the companion GUI."""

    def __init__(self, status_callback=None):
        self.status_callback = status_callback
        self.monitor = None
        self.thread = None

    @property
    def is_running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.is_running:
            return False

        reload_env()
        host = os.getenv('IBKR_HOST', '127.0.0.1')
        port = int(os.getenv('IBKR_PORT', 7496))
        client_id = int(os.getenv('IBKR_CLIENT_ID', '0'))

        self.monitor = TradeMonitor(
            client_id=client_id,
            status_callback=self.status_callback,
            allow_exit=False,
        )

        def _run():
            try:
                if self.status_callback:
                    self.status_callback(f"🔄 Connecting to IBKR on {host}:{port} (client ID {client_id})...")
                self.monitor.connect(host, port, client_id)
                self.monitor.run()
            except Exception as exc:
                if self.status_callback:
                    self.status_callback(f"❌ Monitor error: {exc}")
            finally:
                if self.status_callback:
                    self.status_callback("🛑 Monitoring stopped")

        self.thread = threading.Thread(target=_run, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        if not self.monitor:
            return False
        self.monitor.request_stop()
        return True


def main():
    reload_env()
    app = TradeMonitor(client_id=int(os.getenv('IBKR_CLIENT_ID', '0')), allow_exit=True)

    host = os.getenv('IBKR_HOST', '127.0.0.1')
    port = int(os.getenv('IBKR_PORT', 7496))
    client_id = int(os.getenv('IBKR_CLIENT_ID', '0'))

    print(f"🔄 Connecting to IBKR on {host}:{port} (client ID {client_id})...")
    if client_id != 0:
        print("💡 Tip: Use client ID 0 to receive alerts for orders placed outside this script.")
    if AUTO_STOP_ENABLED:
        print(f"⏰ Auto-stop enabled at {STOP_TIME.strftime('%H:%M')}")
    else:
        print("⏰ Auto-stop disabled — script runs until manually stopped")
    app.connect(host, port, client_id)

    print("👂 Listening for order submissions and fills... (Press Ctrl+C to exit)")
    app.run()

if __name__ == "__main__":
    main()
