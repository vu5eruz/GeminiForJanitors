"""Global HTTP Client."""

from httpx import Client

from ._globals import PROXY_VERSION

http_client = Client(
    headers={
        "User-Agent": f"gfjproxy/{PROXY_VERSION}",
    },
    http2=True,
    timeout=5,
    max_redirects=0,
)
