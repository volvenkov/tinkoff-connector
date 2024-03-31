from datetime import datetime as dt, timedelta
from decimal import Decimal
from enum import Enum
import traceback
import threading
import requests
import math
import pytz
import re


class BaseEnum(str, Enum):
    @classmethod
    def value_of(cls, value):
        for k, v in cls.__members__.items():
            if k == value or v == value:
                return v
        else:
            raise ValueError(f"{cls.__name__} enum not found for {value}")


def send_post_ss(session: requests.Session, url, data, files=None):
    try:
        response = session.post(url, data, files=files)

        try:
            return response.json()
        finally:
            response.close()
    except Exception:
        traceback.print_exc()


def send_tg(session: requests.Session,
            bot_token: str,
            chat_id: str,
            text: str,
            parse_mode: str = None,
            send_async: bool = True):
    url = "https://api.telegram.org/bot" + bot_token + "/sendMessage"

    data = {
        "chat_id": chat_id,
        "text": text,
    }

    if parse_mode is not None:
        data["parse_mode"] = parse_mode

    if send_async:
        threading.Thread(target=send_post_ss, args=(session, url, data)).start()
    else:
        return send_post_ss(session, url, data)


def send_document(session: requests.Session,
                  bot_token: str,
                  chat_id: str,
                  document: bytes,
                  filename: str,
                  caption: str = None,
                  send_async: bool = True):
    url = "https://api.telegram.org/bot" + bot_token + "/sendDocument"

    data = {
        "chat_id": chat_id,
    }

    files = {
        "document": (filename, document)
    }

    if caption is not None:
        data["caption"] = caption

    if send_async:
        threading.Thread(target=send_post_ss, args=(session, url, data, files)).start()
    else:
        return send_post_ss(session, url, data, files)


def reduce_year_from_string(input_string):
    matches = re.findall(r"\d{4}", input_string)

    for match in matches:
        input_string = input_string.replace(match, match[-1])

    return input_string


def round_price(price: Decimal, tick_size: Decimal):
    return round(math.floor(price / tick_size) * tick_size,
                 len(decimal_to_string(tick_size).split('.')[1]))


def decimal_to_string(val: Decimal):
    return format(Decimal(str(val)), "f")


def add_to_set(file_path, element):
    try:
        with open(file_path, "r") as file:
            elements = set(file.read().splitlines())
    except FileNotFoundError:
        elements = set()

    elements.add(element)

    with open(file_path, "w") as file:
        for item in elements:
            file.write("%s\n" % item)


def get_all_elements(file_path):
    try:
        with open(file_path, "r") as file:
            elements = set(file.read().splitlines())

        return elements
    except FileNotFoundError:
        return set()


def is_within_time_window(current_time, windows):
    for window_start, window_end in windows:
        if window_start <= current_time < window_end:
            return True, window_end

    return False, None


def get_utc_time_windows(windows_str):
    utc_now = dt.now(pytz.utc)
    windows = []

    for window in windows_str:
        start, end = window.split("-")

        start_dt = utc_now.replace(hour=int(start.split(":")[0]),
                                   minute=int(start.split(":")[1]),
                                   second=0,
                                   microsecond=0)

        end_dt = utc_now.replace(hour=int(end.split(":")[0]),
                                 minute=int(end.split(":")[1]),
                                 second=0,
                                 microsecond=0)

        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        windows.append((start_dt, end_dt))

    return windows
