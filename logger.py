import traceback
import requests
import utils


class TgLogger:
    def __init__(self, bot_token: str, chat_id: str):
        self._bot_token = bot_token
        self._chat_id = chat_id

        self._session = requests.Session()

    def close(self):
        self._session.close()

    def send_tg(self, msg: str):
        try:
            utils.send_tg(self._session, self._bot_token, self._chat_id, msg, send_async=True)
        except Exception:
            traceback.print_exc()
            pass

    def send_tg_doc(self, caption: str, filename: str):
        try:
            with open(filename, "rb") as file:
                file_content = file.read()

            utils.send_document(self._session, self._bot_token, self._chat_id, file_content, filename, caption)
        except Exception:
            traceback.print_exc()

