from flask import Flask, request
import multiprocessing
import threading
import traceback
import requests
import logging
import typing
import queue
import time


class WebhookServer:
    def __init__(self,
                 ip: str,
                 port: int,
                 ssl_context: typing.Tuple[str, str],
                 ip_whitelist: list[str],
                 webhook_queue: queue.Queue):
        self._ip = ip
        self._port = port
        self._ssl_context = ssl_context
        self._ip_whitelist = ip_whitelist
        self._webhook_queue = webhook_queue

        self._ip_whitelist.append(self._ip)

        self._app = Flask(__name__)

        @self._app.before_request
        def limit_remote_addr():
            if request.remote_addr not in ip_whitelist:
                return "Access denied", 403

        @self._app.route("/webhook", methods=["POST"])
        def webhook():
            webhook_queue.put(request.get_json())

            return ""

        @self._app.route("/ping", methods=["GET", "POST"])
        def ping():
            return "pong"

    def _run(self):
        self._app.run(host=self._ip,
                      port=self._port,
                      ssl_context=self._ssl_context)

    @staticmethod
    def run_flask(ip: str,
                  port: int,
                  ssl_context: typing.Tuple[str, str],
                  ip_whitelist: list[str],
                  webhook_queue: queue.Queue):
        webhook_server = WebhookServer(ip,
                                       port,
                                       ssl_context,
                                       ip_whitelist,
                                       webhook_queue)

        webhook_server._run()


class WebhookServerManager:
    def __init__(self,
                 ip: str,
                 port: int,
                 ssl_context: typing.Tuple[str, str],
                 ip_whitelist: list[str],
                 webhook_queue: queue.Queue):
        self._ip = ip
        self._port = port
        self._ssl_context = ssl_context
        self._ip_whitelist = ip_whitelist
        self._webhook_queue = webhook_queue

        self._server_process = None

        self._stop_event = threading.Event()

        self._server_checker_thread = threading.Thread(target=self._server_checker)

    def start(self):
        self._run_flask()

        self._server_checker_thread.start()

    def stop(self):
        self._stop_event.set()

        logging.info(f"Starting to stop server...")

        if self._server_checker_thread.is_alive():
            self._server_checker_thread.join()

        logging.info(f"Server checker stopped.")

        if self._server_process is not None and self._server_process.is_alive():
            self._server_process.terminate()

            self._server_process.join()

        logging.info(f"Server process stopped.")

    def _run_flask(self):
        st = time.time()

        self._server_process = multiprocessing.Process(
            target=WebhookServer.run_flask,
            args=(self._ip, self._port, self._ssl_context, self._ip_whitelist, self._webhook_queue))

        self._server_process.start()

        max_attempts, attempt = 20, 0

        while attempt < max_attempts:
            try:
                requests.get(f"https://{self._ip}:{self._port}/ping",
                             verify=False,
                             timeout=10)

                logging.info(f"Server started in {(time.time() - st):.2f}s!")

                return
            except Exception:
                time.sleep(0.5)

                attempt += 1

        logging.error(f"Something went wrong during starting server!")

    def _server_checker(self):
        while not self._stop_event.is_set():
            restart_server = False

            try:
                logging.info("Sending ping to server...")

                response = \
                    requests.get(f"https://{self._ip}:{self._port}/ping",
                                 verify=False,
                                 timeout=10)

                logging.info("Ping response received from server.")

                if response.status_code == 200 and response.text == "pong":
                    logging.info("Server is up!")
                else:
                    restart_server = True

                    logging.error("Server is down, restarting...")
            except requests.RequestException as ex:
                restart_server = True

                logging.error(f"Error pinging server: {ex.__class__.__name__} {ex}, restarting server...")

            if restart_server:
                try:
                    logging.info(f"Termination of server process started...")

                    if self._server_process is not None and self._server_process.is_alive():
                        self._server_process.terminate()

                        self._server_process.join()

                    logging.info(f"Termination of server process ended!")

                    self._run_flask()
                except Exception:
                    traceback.print_exc()

            time.sleep(10)
