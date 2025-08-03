"""Utilities."""

import atexit
import click
import re
import requests
import subprocess
import time
import threading

################################################################################


def _runner(cloudflared: str) -> str:
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


def run_cloudflared(cloudflared: str) -> str:
    runner_thread = threading.Thread(target=_runner, args=(cloudflared,), daemon=True)
    runner_thread.start()


################################################################################
