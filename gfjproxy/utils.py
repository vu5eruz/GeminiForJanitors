"""Utilities."""

import atexit
import click
import json
import re
import requests
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from flask import Response

################################################################################


class MessageKind(Enum):
    CHAT = 0
    ERROR = 1
    PROXY = 2


@dataclass(frozen=True, kw_only=True)
class ResponseMessage:
    """Response message model."""

    kind: MessageKind

    text: str

    status_code: int = None


class ResponseHelper:
    """Response helper to provide JanitorAI with valid responses."""

    def __init__(self, *, wrap_errors: bool = False):
        self._messages = []
        self._status = 200
        self._wrap_errors = wrap_errors

    def add_error(self, message, status_code: int):
        self._messages.append(
            ResponseMessage(
                kind=MessageKind.ERROR,
                text=str(message),
                status_code=status_code,
            )
        )
        self._status = status_code
        return self

    def add_message(self, *messages):
        for message in messages:
            self._messages.append(
                ResponseMessage(kind=MessageKind.CHAT, text=str(message))
            )
        return self

    def add_proxy_message(self, *messages):
        for message in messages:
            self._messages.append(
                ResponseMessage(kind=MessageKind.PROXY, text=str(message))
            )
        return self

    def build(self) -> Response:
        if self._status != 200 and len(self._messages) == 1:
            if self._wrap_errors:
                return Response(
                    response=[json.dumps({"error": self.message.strip()})],
                    status=self._status,
                    content_type="application/json; charset=utf-8",
                )
            else:
                return Response(
                    response=[self.message],
                    status=self._status,
                    content_type="text/plain; charset=utf-8",
                )
        else:  # self._status == 200 or complex multi-line message
            return Response(
                response=[
                    json.dumps(
                        {
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": self.message,
                                    },
                                    "finish_reason": "stop",
                                }
                            ]
                        }
                    )
                ],
                status=200,
                content_type="application/json; charset=utf-8",
            )

    def build_error(self, message, status_code: int):
        return self.add_error(message, status_code).build()

    def build_message(self, *messages):
        return self.add_message(*messages).build()

    @property
    def message(self) -> str:
        if not self._messages:
            return ""

        if len(self._messages) == 1:
            if self._messages[0].kind == MessageKind.CHAT:
                return self._messages[0].text
            if self._messages[0].kind == MessageKind.ERROR:
                if self._wrap_errors:
                    return f"PROXY ERROR {self._messages[0].status_code}: {self._messages[0].text}"
                return self._messages[0].text
            return f"<proxy>{self._messages[0].text}\n</proxy>"

        last_msg = self._messages[0].kind
        proxy_msg_group = last_msg == MessageKind.PROXY
        result = []

        if proxy_msg_group:
            result.append("<proxy>")

        for i, msg in enumerate(self._messages):
            if msg.kind == last_msg:
                prefix = ""
            elif msg.kind != MessageKind.CHAT:
                prefix = "<proxy>" if not proxy_msg_group else ""
                proxy_msg_group = True
            elif proxy_msg_group:
                prefix = "</proxy>"
                proxy_msg_group = False
            else:
                prefix = ""

            if msg.kind == MessageKind.ERROR:
                if self._wrap_errors or proxy_msg_group:
                    text = f"PROXY ERROR {msg.status_code}: {msg.text}"
                    text = f"Error {msg.status_code}: {msg.text}\n"
                else:
                    text = msg.text
            elif i != len(self._messages) - 1:  # Is this last msg
                text = f"{msg.text}\n"
            else:
                text = msg.text

            result.append(f"{prefix}{text}")

            # TODO: Invariant: result[-1] always ends with a \n before last msg

            last_msg = msg.kind

        if proxy_msg_group:
            if not result[-1].endswith("\n"):
                result.append("\n")
            result.append("</proxy>")

        return "".join(result)

    @property
    def status(self) -> int:
        return self._status

    @property
    def status_code(self) -> int:
        click.echo("!!! Don't use .status_code on a ResponseHelper!!!")
        return self.build().status_code

    @property
    def response(self) -> int:
        click.echo("!!! Don't use .response on a ResponseHelper!!!")
        return self.build().response


################################################################################


def is_proxy_test(request_json: dict) -> bool:
    # A normal chat request has 2 or more messages and the first one always has
    # "role" set to "system" (this being the bot description). Meanwhile, a
    # proxy test request looks like this:
    #   {
    #     "max_tokens": 10,
    #     "messages": [{"content": "Just say TEST", "role": "user"}],
    #     "model": "gemini-2.5-pro",
    #     "temperature": 0
    #   }
    # We need to inspect the "messages" key. Everything else can vary.
    # A false negative will lead the request down the regular chat path, which
    # isn't really a big deal, considering the error feedback UI will only fail
    # to display any proxy errors and will show something else instead.

    messages = request_json.get("messages")
    if isinstance(messages, list) and len(messages) == 1:
        message = messages[0]
        if isinstance(message, dict):
            text = message.get("content")
            role = message.get("role")
            if text == "Just say TEST" and role == "user":
                # Yep, looks like a proxy test
                return True

    # Most likely not a proxy test request
    return False


################################################################################


def _runner(cloudflared: str):
    click.echo(" * Running cloudflared ...")

    process = subprocess.Popen(
        [
            cloudflared,
            "tunnel",
            "--metrics",
            "127.0.0.1:5001",
            "--url",
            "http://127.0.0.1:5000",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    atexit.register(process.terminate)

    for _ in range(10):
        try:
            metrics = requests.get("http://127.0.0.1:5001/metrics").text
            url = re.search(
                r"(?P<url>https?:\/\/[^\s]+.trycloudflare.com)", metrics
            ).group("url")
            click.echo(f" * Tunnel on {url}")
            return
        except requests.exceptions.RequestException:
            time.sleep(1)
    else:
        click.echo(" * Couldn't get cloudflared link")


def run_cloudflared(cloudflared: str):
    runner_thread = threading.Thread(target=_runner, args=(cloudflared,), daemon=True)
    runner_thread.start()


################################################################################
