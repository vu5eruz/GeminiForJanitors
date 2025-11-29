"""GeminiForJanitors: Google AI Studio Proxy for JanitorAI"""

################################################################################

# Make sure START_TIME is initialized as early as possible
from .start_time import START_TIME  # noqa: F401

from ._globals import PROXY_AUTHORS, PROXY_VERSION

__all__ = [
    "PROXY_AUTHORS",
    "PROXY_VERSION",
]

__author__ = PROXY_AUTHORS

__version__ = PROXY_VERSION

################################################################################
