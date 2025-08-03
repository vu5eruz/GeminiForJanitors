"""GeminiForJanitors: Google AI Studio Proxy for JanitorAI"""

from ._globals import PROXY_AUTHORS, PROXY_VERSION
from .app import app

__all__ = [
    "app",
    "PROXY_AUTHORS",
    "PROXY_VERSION",
]

__author__ = PROXY_AUTHORS

__version__ = PROXY_VERSION
