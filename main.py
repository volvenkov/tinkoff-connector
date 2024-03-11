import multiprocessing
import logging
import urllib3
import signal

import server
import bot
import cfg


# bonds - облигации
# etfs - инвестиционных фондов
# futures - фьючерсы
# options - опционы
# shares - акции
# indicatives - индикативные инструменты (индексов, товаров и др.)


def stop(_signal, _frame):
    wsm.stop()

    bot.stop()


if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    logging.basicConfig(level=logging.DEBUG, filename="logs.log", filemode="w",
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    logging.getLogger().addHandler(console_handler)

    signal.signal(signal.SIGINT, stop)

    webhook_queue = multiprocessing.Queue()

    bot = bot.Bot(cfg.account_name, cfg.tinkoff_token, cfg.currency, webhook_queue)

    bot.start()

    wsm = server.WebhookServerManager(cfg.ip,
                                      cfg.port,
                                      (cfg.cert_path, cfg.key_path),
                                      cfg.ip_whitelist,
                                      webhook_queue)

    wsm.start()
