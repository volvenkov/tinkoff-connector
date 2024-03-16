from enum import Enum
import traceback
import threading
import requests
import re


class BaseEnum(str, Enum):
    @classmethod
    def value_of(cls, value):
        for k, v in cls.__members__.items():
            if k == value or v == value:
                return v
        else:
            raise ValueError(f"{cls.__name__} enum not found for {value}")


def send_post_ss(session: requests.Session, url, data):
    try:
        response = session.post(url, data)

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


def reduce_year_from_string(input_string):
    matches = re.findall(r"\d{4}", input_string)

    for match in matches:
        input_string = input_string.replace(match, match[-1])

    return input_string
