from tinkoff.invest import (OrderDirection, OrderType, StopOrderDirection, StopOrderType, StopOrderExpirationType,
                            ExchangeOrderType, StopOrderStatusOption, OrderExecutionReportStatus, OrderState)
from tinkoff.invest.utils import decimal_to_quotation, money_to_decimal
from tinkoff.invest import Client, Share, Future, Etf
from collections import defaultdict
from decimal import Decimal
import threading
import logging
import typing
import queue
import time

import tinkoff_utils as tu
import utils


class InstrumentNotFoundException(Exception):
    pass


class UnsupportedPositionSideException(Exception):
    pass


class BalanceNonZeroException(Exception):
    pass


class BalanceNotFoundException(Exception):
    pass


class IllegalQtyException(Exception):
    pass


class UnsupportedTypeException(Exception):
    pass


class NothingToCloseException(Exception):
    pass


class IllegalOrderStatusException(Exception):
    pass


class WebhookType(utils.BaseEnum):
    OPEN = "open"
    RENEW_STOP_LOSS = "renew_stop_loss"
    CLOSE = "close"


class PositionSide(utils.BaseEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class Bot:
    def __init__(self,
                 account_name: str,
                 tinkoff_token: str,
                 currency: str,
                 max_verify_attempts: int,
                 verify_delay_s: float,
                 send_msg: typing.Callable[[str], typing.Any],
                 webhook_queue: queue.Queue):
        self._account_name = account_name
        self._tinkoff_token = tinkoff_token
        self._currency = currency
        self._max_verify_attempts = max_verify_attempts
        self._verify_delay_s = verify_delay_s
        self._send_msg = send_msg
        self._webhook_queue = webhook_queue

        self._account_id = None

        self._stop_event = threading.Event()

        self._instruments_updater_thread = threading.Thread(target=self._instruments_updater)

        self._instruments: dict[str, dict[str, Future | Share | Etf]] = {}
        self._instruments_by_uid: dict[str, Future | Share | Etf] = {}
        self._instruments_lock = threading.Lock()

        self._webhook_handler_thread = threading.Thread(target=self._webhook_handler)

    def start(self):
        with Client(self._tinkoff_token) as client:
            account_id = tu.get_account_id(client, self._account_name)

        if account_id is None:
            raise tu.AccountNotFoundException(f"Account '{self._account_name}' not found!")

        self._account_id = account_id

        self._instruments_updater_thread.start()

        self._webhook_handler_thread.start()

    def stop(self):
        self._stop_event.set()

        logging.info(f"Starting to stop bot...")

        if self._webhook_handler_thread.is_alive():
            self._webhook_handler_thread.join()

        logging.info(f"Webhook handler stopped.")

        if self._instruments_updater_thread.is_alive():
            self._instruments_updater_thread.join()

        logging.info(f"Instruments updater stopped.")

    def _instruments_updater(self):
        while not self._stop_event.is_set():
            try:
                with Client(self._tinkoff_token) as client:
                    instruments = defaultdict(dict)

                    instruments_by_uid = {}

                    for method in ["futures", "shares", "etfs"]:
                        for item in getattr(client.instruments, method)().instruments:
                            instruments[item.ticker][item.currency] = item

                            instruments_by_uid[item.uid] = item
            except Exception as ex:
                self._send_msg(f"❌ Error occurred during instrument list update: {ex.__class__.__name__} {ex}")

                continue

            with self._instruments_lock:
                self._instruments = instruments
                self._instruments_by_uid = instruments_by_uid

            time.sleep(60)

    def _webhook_handler(self):
        while not self._stop_event.is_set():
            try:
                msg = self._on_webhook(self._webhook_queue.get(timeout=1))

                self._send_msg(msg)
            except queue.Empty:
                continue
            except Exception as ex:
                self._send_msg(f"❌ Error occurred: {ex.__class__.__name__} {ex}")

    def _on_webhook(self, webhook_json: dict) -> str:
        webhook_type = WebhookType.value_of(webhook_json["type"])

        ticker = webhook_json["ticker"]
        position_side = PositionSide.value_of(webhook_json["position_side"])

        with self._instruments_lock:
            if ticker not in self._instruments or self._currency not in self._instruments[ticker]:
                raise InstrumentNotFoundException(f"Instrument '{ticker}' '{self._currency}' not found!")

            instrument = self._instruments[ticker][self._currency]

        if instrument.__class__.__name__ not in [Future.__name__, Share.__name__, Etf.__name__]:
            raise UnsupportedTypeException(
                f"Unsupported type exception: {instrument.__class__.__name__},"
                f"supported {Share.__name__}, {Future.__name__} and {Etf.__name__}!")

        if instrument.__class__.__name__ != Future.__name__ and position_side != PositionSide.LONG:
            raise UnsupportedPositionSideException(
                f"Unsupported position side for {instrument.__class__.__name__} '{ticker}' '{self._currency}': "
                f"{position_side.value}!")

        if webhook_type == WebhookType.OPEN:
            qty = int(webhook_json["qty"])

            tp_price = Decimal(webhook_json["tp_price"]) if "tp_price" in webhook_json else None
            sl_price = Decimal(webhook_json["sl_price"]) if "sl_price" in webhook_json else None

            if qty % instrument.lot != 0:
                qty = int(qty / instrument.lot) * instrument.lot

            if qty <= 0:
                raise IllegalQtyException(f"Invalid quantity for '{ticker}' '{self._currency}': {qty}, "
                                          f"lot: {instrument.lot}!")

            with Client(self._tinkoff_token) as client:
                current_balance = self._get_balance(client, instrument)

                if current_balance is None:
                    raise BalanceNotFoundException(f"Balance for '{ticker}' '{self._currency}' not found!")

                if current_balance != 0:
                    raise BalanceNonZeroException(
                        f"Balance for '{ticker}' '{self._currency}' non zero: {current_balance}!")

                # if instrument.__class__.__name__ == Future.__name__:
                #     print(client.users.get_margin_attributes(account_id=self._account_id))
                #     # GetMarginAttributesResponse(liquid_portfolio=MoneyValue(currency='rub', units=493, nano=680000000), starting_margin=MoneyValue(currency='rub', units=443, nano=890000000), minimal_margin=MoneyValue(currency='rub', units=221, nano=950000000), funds_sufficiency_level=Quotation(units=1, nano=230000000), amount_of_missing_funds=MoneyValue(currency='rub', units=-49, nano=-790000000), corrected_margin=MoneyValue(currency='rub', units=443, nano=890000000))
                #     response = client.instruments.get_futures_margin(figi=instrument.figi)  # replace to uid
                #
                #     initial_margin_on_buy, initial_margin_on_sell = money_to_decimal(response.initial_margin_on_buy), \
                #         money_to_decimal(response.initial_margin_on_sell)
                #
                #     print(f"{initial_margin_on_buy * qty} {initial_margin_on_sell * qty}")
                #
                #     return ""

                response = client.orders.post_order(
                    instrument_id=instrument.uid,
                    quantity=qty,
                    account_id=self._account_id,
                    direction=OrderDirection.ORDER_DIRECTION_BUY if position_side == PositionSide.LONG
                    else OrderDirection.ORDER_DIRECTION_SELL,
                    order_type=OrderType.ORDER_TYPE_MARKET
                )

                order_state = self._wait_till_status(client,
                                                     response.order_id,
                                                     OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL,
                                                     [OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_CANCELLED,
                                                      OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_REJECTED])

                if tp_price:
                    self._place_tp(client, qty, instrument.uid, tp_price, position_side)

                if sl_price:
                    self._place_sl(client, qty, instrument.uid, sl_price, position_side)

                return f"✅ '{ticker}' '{self._currency}' position opened on price " \
                       f"{money_to_decimal(order_state.executed_order_price)} | tp: {tp_price} | sl: {sl_price}"
        elif webhook_type == WebhookType.RENEW_STOP_LOSS:
            sl_price = Decimal(webhook_json["sl_price"])
            qty = int(webhook_json["qty"])

            with Client(self._tinkoff_token) as client:
                response = client.stop_orders.get_stop_orders(account_id=self._account_id,
                                                              status=StopOrderStatusOption.STOP_ORDER_STATUS_ACTIVE)

                stop_loss_order_ids = \
                    [stop_order.stop_order_id for stop_order in response.stop_orders if
                     stop_order.order_type == StopOrderType.STOP_ORDER_TYPE_STOP_LOSS and
                     stop_order.instrument_uid == instrument.uid]

                for stop_loss_order_id in stop_loss_order_ids:
                    client.stop_orders.cancel_stop_order(account_id=self._account_id,
                                                         stop_order_id=stop_loss_order_id)

                self._place_sl(client, qty, instrument.uid, sl_price, position_side)

            return f"✅ '{ticker}' '{self._currency}' sl price changed to {sl_price} "
        elif webhook_type == WebhookType.CLOSE:
            with Client(self._tinkoff_token) as client:
                response = client.stop_orders.get_stop_orders(account_id=self._account_id,
                                                              status=StopOrderStatusOption.STOP_ORDER_STATUS_ACTIVE)

                stop_order_ids = \
                    [stop_order.stop_order_id for stop_order in response.stop_orders if
                     stop_order.instrument_uid == instrument.uid]

                for stop_order_id in stop_order_ids:
                    client.stop_orders.cancel_stop_order(account_id=self._account_id,
                                                         stop_order_id=stop_order_id)

                current_balance = self._get_balance(client, instrument)

                if current_balance is None:
                    raise BalanceNotFoundException(f"Balance for '{ticker}' '{self._currency}' not found!")

                if current_balance == 0:
                    raise NothingToCloseException(
                        f"Nothing to close for '{ticker}' '{self._currency}', balance: {current_balance}!")

                response = client.orders.post_order(
                    instrument_id=instrument.uid,
                    quantity=current_balance,
                    account_id=self._account_id,
                    direction=OrderDirection.ORDER_DIRECTION_SELL if position_side == PositionSide.LONG
                    else OrderDirection.ORDER_DIRECTION_BUY,
                    order_type=OrderType.ORDER_TYPE_MARKET
                )

                order_state = self._wait_till_status(
                    client,
                    response.order_id,
                    OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL,
                    [OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_CANCELLED,
                     OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_REJECTED])

                return f"✅ '{ticker}' '{self._currency}' position closed on price " \
                       f"{money_to_decimal(order_state.executed_order_price)} | orders cancelled"

    def _wait_till_status(self,
                          client,
                          order_id: str,
                          required_order_status: OrderExecutionReportStatus,
                          break_order_status: list[OrderExecutionReportStatus]) -> OrderState:
        for i in range(self._max_verify_attempts):
            order_status = None

            try:
                response = client.orders.get_order_state(account_id=self._account_id, order_id=order_id)

                order_status = response.execution_report_status

                if order_status in break_order_status:
                    raise IllegalOrderStatusException(
                        f"Illegal order status with id: {order_id}, {order_status.value}!")

                if order_status == required_order_status:
                    return response
            except Exception:
                pass

            if i == self._max_verify_attempts - 1:
                raise IllegalOrderStatusException(f"Illegal order status with id: {order_id}, {order_status.value}!")

            time.sleep(self._verify_delay_s)

    def _get_balance(self, client, instrument) -> int | None:
        positions = client.operations.get_positions(account_id=self._account_id)

        if instrument.__class__.__name__ in [Share.__name__, Etf.__name__]:
            positions = positions.securities
        elif instrument.__class__.__name__ == Future.__name__:
            positions = positions.futures
        else:
            return None

        current_balance = 0

        for position in positions:
            if position.instrument_uid == instrument.uid:
                current_balance = position.balance

                break

        return current_balance

    def _place_tp(self, client, qty: int, uid: str, price: Decimal, position_side: PositionSide):
        return client.stop_orders.post_stop_order(
            quantity=qty,
            instrument_id=uid,
            price=decimal_to_quotation(price),
            stop_price=decimal_to_quotation(price),
            direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL if position_side == PositionSide.LONG
            else StopOrderDirection.STOP_ORDER_DIRECTION_BUY,
            account_id=self._account_id,
            expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL,
            stop_order_type=StopOrderType.STOP_ORDER_TYPE_TAKE_PROFIT,
            exchange_order_type=ExchangeOrderType.EXCHANGE_ORDER_TYPE_MARKET,
        )

    def _place_sl(self, client, qty: int, uid: str, price: Decimal, position_side: PositionSide):
        return client.stop_orders.post_stop_order(
            quantity=qty,
            instrument_id=uid,
            price=decimal_to_quotation(price),
            stop_price=decimal_to_quotation(price),
            direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL if position_side == PositionSide.LONG
            else StopOrderDirection.STOP_ORDER_DIRECTION_BUY,
            account_id=self._account_id,
            expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL,
            stop_order_type=StopOrderType.STOP_ORDER_TYPE_STOP_LOSS,
            exchange_order_type=ExchangeOrderType.EXCHANGE_ORDER_TYPE_MARKET,
        )
