from tinkoff.invest import OrderDirection, OrderType
from tinkoff.invest import Client
from decimal import Decimal
import threading
import traceback
import logging
import queue
import uuid

import tinkoff_utils as tu
import utils


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
                 webhook_queue: queue.Queue):
        self._account_name = account_name
        self._tinkoff_token = tinkoff_token
        self._webhook_queue = webhook_queue

        self._account_id = None

        self._stop_event = threading.Event()

        self._webhook_handler_thread = threading.Thread(target=self._webhook_handler)

    def start(self):
        with Client(self._tinkoff_token) as client:
            account_id = tu.get_account_id(client, self._account_name)

        if account_id is None:
            raise tu.AccountNotFoundException(f"Account '{self._account_name}' not found!")

        self._account_id = account_id

        self._webhook_handler_thread.start()

    def stop(self):
        self._stop_event.set()

        logging.info(f"Starting to stop bot...")

        if self._webhook_handler_thread.is_alive():
            self._webhook_handler_thread.join()

        logging.info(f"Webhook handler stopped.")

    def _webhook_handler(self):
        while not self._stop_event.is_set():
            try:
                self._on_webhook(self._webhook_queue.get(timeout=1))
            except queue.Empty:
                continue
            except Exception:
                traceback.print_exc()

    def _on_webhook(self, webhook_json: dict):
        webhook_type = WebhookType.value_of(webhook_json["type"])

        ticker = webhook_json["ticker"]

        if webhook_type == WebhookType.OPEN:
            position_side = PositionSide.value_of(webhook_json["position_side"])
            qty = int(webhook_json["qty"])

            tp_price = Decimal(webhook_json["tp_price"]) if "tp_price" in webhook_json else None
            sl_price = Decimal(webhook_json["sl_price"]) if "sl_price" in webhook_json else None

            # verify no position exists
            # verify lot

            # LONG/SHORT ???

            order_id = uuid.uuid4()

            with Client(self._tinkoff_token) as client:
                response = client.orders.post_order(
                    order_id=order_id,
                    instrument_id="",
                    quantity=qty,
                    account_id=self._account_id,
                    direction=OrderDirection.ORDER_DIRECTION_BUY if position_side == PositionSide.LONG
                    else OrderDirection.ORDER_DIRECTION_SELL,
                    order_type=OrderType.ORDER_TYPE_MARKET
                )

            # place entry order

            # wait entry order execution

            if tp_price:
                # decimal_to_quotation(tp_price)

                pass  # place tp

            if sl_price:
                # decimal_to_quotation(sl_price)

                pass  # place sl
        elif webhook_type == WebhookType.RENEW_STOP_LOSS:
            sl_price = Decimal(webhook_json["sl_price"])

        elif webhook_type == WebhookType.CLOSE:
            pass
