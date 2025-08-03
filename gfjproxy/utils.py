"""Utilities."""

import atexit
import click
import re
import requests
import subprocess
import time
import threading

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
