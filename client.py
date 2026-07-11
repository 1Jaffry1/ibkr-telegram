import os
import sys
from datetime import datetime, time
from dotenv import load_dotenv
from ibapi.client import EClient
from ibapi.common import UNSET_DOUBLE
from ibapi.wrapper import EWrapper
import requests

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

OPTION_SEC_TYPES = {'OPT', 'FOP', 'IOPT'}
SUBMISSION_STATUSES = {'Submitted', 'PreSubmitted', 'PendingSubmit'}

def getenv_or_default(key, default):
    value = os.getenv(key)
    if value is None or not str(value).strip():
        return default
    return value

# Load custom messages from .env
CONNECTED_MESSAGE = getenv_or_default('CONNECTED_MESSAGE', '✅ Connected to IBKR. Ready for trades.')
CLOSED_MESSAGE = getenv_or_default('CLOSED_MESSAGE', '📊 Market closed. Trade monitor stopping.')

ORDER_MESSAGE_TEMPLATE = getenv_or_default('ORDER_MESSAGE', """📝 *ORDER SUBMITTED*

*Symbol:* `{symbol}`
*Exchange:* `{exchange}`
*Action:* `{action}`
*Quantity:* `{quantity}`
*Type:* `{order_type}`
*Price:* `{limit_price}`
*Status:* `{status}`""")

ORDER_OPTION_MESSAGE_TEMPLATE = getenv_or_default('ORDER_OPTION_MESSAGE', """📝 *OPTION ORDER SUBMITTED*

*Underlying:* `{symbol}`
*Contract:* `{contract_description}`
*Action:* `{action}`
*Contracts:* `{quantity}`
*Type:* `{order_type}`
*Price:* `{limit_price}`
*Status:* `{status}`""")

TRADE_MESSAGE_TEMPLATE = getenv_or_default('TRADE_MESSAGE', """✅ *ORDER FILLED*

*Symbol:* `{symbol}`
*Exchange:* `{exchange}`
*Action:* `{side}`
*Quantity:* `{quantity}`
*Price:* `${price}`
*Commission:* `${commission}`
*Time:* `{time}`
*Account:* `{account}`""")

OPTION_MESSAGE_TEMPLATE = getenv_or_default('OPTION_MESSAGE', """✅ *OPTION ORDER FILLED*

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
*Account:* `{account}`""")

# Parse stop time
stop_time_str = os.getenv('STOP_TIME', '16:00')
try:
    stop_hour, stop_minute = map(int, stop_time_str.split(':'))
    STOP_TIME = time(stop_hour, stop_minute)
except:
    STOP_TIME = time(16, 0)

def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

AUTO_STOP_ENABLED = parse_bool(os.getenv('AUTO_STOP_ENABLED'), default=True)

def should_auto_stop():
    return AUTO_STOP_ENABLED and datetime.now().time() >= STOP_TIME

def is_option_contract(contract):
    return contract.secType in OPTION_SEC_TYPES

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
    return contract.symbol

def build_contract_context(contract):
    return {
        'symbol': contract.symbol,
        'exchange': contract.exchange,
        'contract_description': build_contract_description(contract),
        'option_type': format_option_type(contract.right),
        'strike': contract.strike if is_option_contract(contract) else '',
        'expiry': format_expiry(contract.lastTradeDateOrContractMonth) if is_option_contract(contract) else '',
        'local_symbol': contract.localSymbol or contract.symbol,
        'sec_type': contract.secType,
    }

def build_order_context(contract, order, status=''):
    context = build_contract_context(contract)
    context.update({
        'action': order.action,
        'quantity': int(order.totalQuantity),
        'order_type': order.orderType,
        'limit_price': format_limit_price(order),
        'status': status,
    })
    return context

def build_trade_context(contract, execution, commission):
    quantity = int(execution.shares)
    context = build_contract_context(contract)
    context.update({
        'side': execution.side,
        'quantity': quantity,
        'price': execution.price,
        'commission': commission,
        'time': execution.time,
        'account': execution.acctNumber,
    })
    return context

def format_order_message(contract, order, status=''):
    context = build_order_context(contract, order, status)
    template = ORDER_OPTION_MESSAGE_TEMPLATE if is_option_contract(contract) else ORDER_MESSAGE_TEMPLATE
    return template.format(**context)

def format_trade_message(contract, execution, commission):
    context = build_trade_context(contract, execution, commission)
    template = OPTION_MESSAGE_TEMPLATE if is_option_contract(contract) else TRADE_MESSAGE_TEMPLATE
    return template.format(**context)

def send_telegram_message(message, reply_to=None, silent=False):
    """Send message via Telegram. Returns message_id on success."""
    if not message or not str(message).strip():
        print("⚠️  Skipping empty Telegram message")
        return None

    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
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
    def __init__(self, client_id):
        EClient.__init__(self, self)
        self.client_id = client_id
        self.nextOrderId = None
        self.orders_by_perm_id = {}
        self.orders_by_order_id = {}
        self.order_status_by_perm_id = {}
        self.submission_message_ids = {}
        self.last_execution_by_perm_id = {}
        self.notified_submissions = set()
        self.notified_fills = set()
        self.pending_executions = {}

    def nextValidId(self, orderId):
        self.nextOrderId = orderId
        print(CONNECTED_MESSAGE)
        send_telegram_message(CONNECTED_MESSAGE)
        self._subscribe_to_orders()

    def _subscribe_to_orders(self):
        if self.client_id == 0:
            print("🔗 Binding manual orders (client ID 0)...")
            self.reqAutoOpenOrders(True)
            self.reqOpenOrders()
        else:
            print("⚠️  Client ID is not 0 — manual orders may not be detected.")
            print("   Fix: set Client ID to 0 in settings, or set Master API Client ID to match in TWS/Gateway.")
            self.reqAllOpenOrders()

    def openOrder(self, orderId, contract, order, orderState):
        if should_auto_stop():
            self._handle_auto_stop()
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

        print(
            f"📋 openOrder: {build_contract_description(contract)} "
            f"status={state_status or 'n/a'} permId={perm_id} orderId={orderId}"
        )
        self._try_notify_submission(perm_id, state_status)

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId,
                    parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
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

        print(
            f"📊 orderStatus: permId={permId} orderId={orderId} "
            f"status={status} filled={filled} remaining={remaining}"
        )

        if status in SUBMISSION_STATUSES:
            self._try_notify_submission(permId, status)
        elif status == 'Filled':
            self._try_notify_fill(permId)
        elif remaining == 0 and filled > 0:
            self._try_notify_fill(permId)

    def execDetails(self, reqId, contract, execution):
        if should_auto_stop():
            self._handle_auto_stop()
            return

        self.pending_executions[execution.execId] = (contract, execution)
        self.last_execution_by_perm_id[execution.permId] = (contract, execution)
        print(
            f"💱 execDetails: {build_contract_description(contract)} "
            f"permId={execution.permId} qty={execution.shares} price={execution.price}"
        )

    def commissionReport(self, commissionReport):
        pending = self.pending_executions.pop(commissionReport.execId, None)
        if not pending:
            return

        contract, execution = pending
        self.last_execution_by_perm_id[execution.permId] = (contract, execution, commissionReport.commission)
        self._try_notify_fill(execution.permId)

    def execDetailsEnd(self, reqId):
        for exec_id, (contract, execution) in list(self.pending_executions.items()):
            self.last_execution_by_perm_id[execution.permId] = (contract, execution, 0)
            self._try_notify_fill(execution.permId)
            del self.pending_executions[exec_id]

    def _perm_id_for_order(self, order_id):
        return self.orders_by_order_id.get(order_id, order_id)

    def _handle_auto_stop(self):
        print(f"⏰ {CLOSED_MESSAGE}")
        send_telegram_message(CLOSED_MESSAGE)
        self.disconnect()
        sys.exit(0)

    def _try_notify_submission(self, perm_id, status=''):
        if perm_id in self.notified_submissions:
            return

        order_info = self.orders_by_perm_id.get(perm_id)
        if not order_info:
            return

        status_info = self.order_status_by_perm_id.get(perm_id, {})
        current_status = status or status_info.get('status', '')
        if current_status in ('Cancelled', 'Inactive', 'ApiCancelled', 'Filled'):
            if current_status != 'Filled':
                return

        contract = order_info['contract']
        order = order_info['order']
        message = format_order_message(
            contract, order,
            'Submitted' if current_status == 'Filled' else (current_status or 'Submitted')
        )
        label = build_contract_description(contract)
        message_id = send_telegram_message(message)

        if message_id:
            self.notified_submissions.add(perm_id)
            self.submission_message_ids[perm_id] = message_id
            print(f"📤 Order submitted alert sent for {label}")
        else:
            print(f"❌ Failed to send order submitted alert for {label}")

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

        trade_msg = format_trade_message(contract, execution, commission)
        label = build_contract_description(contract)
        reply_to = self.submission_message_ids.get(perm_id)
        message_id = send_telegram_message(trade_msg, reply_to=reply_to, silent=True)

        if message_id:
            self.notified_fills.add(perm_id)
            print(f"✅ Fill alert sent for {label}")
        else:
            print(f"❌ Failed to send fill alert for {label}")

    def error(self, reqId, errorCode, errorString):
        if errorCode not in (1100, 2104, 2106, 2158):
            print(f"❌ Error {errorCode}: {errorString}")

    def connectionClosed(self):
        print("⚠️  Connection closed. Reconnecting...")
        import time
        time.sleep(5)
        self.connect(
            os.getenv('IBKR_HOST'),
            int(os.getenv('IBKR_PORT')),
            int(os.getenv('IBKR_CLIENT_ID', '0'))
        )

def main():
    app = TradeMonitor(client_id=int(os.getenv('IBKR_CLIENT_ID', '0')))

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
