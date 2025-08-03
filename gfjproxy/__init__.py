"""GFJ Proxy."""

from .app import app
from .globals import PROXY_AUTHORS, PROXY_VERSION
from .xuiduser import (
    XUID,
    LocalUserStorage,
    RedisUserStorage,
    UserSettings,
    UserStorage,
)

__all__ = [
    "app",
    "PROXY_AUTHORS",
    "PROXY_VERSION",
    "XUID",
    "LocalUserStorage",
    "RedisUserStorage",
    "UserSettings",
    "UserStorage",
]

__author__ = PROXY_AUTHORS
__version__ = PROXY_VERSION
