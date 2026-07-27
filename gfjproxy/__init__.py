"""GeminiForJanitors: Google AI Studio Proxy for JanitorAI"""

################################################################################

# Make sure START_TIME is initialized as early as possible
# ruff: disable[I001]
from .start_time import START_TIME

from ._globals import PROXY_AUTHORS, PROXY_VERSION

__all__ = [
    "PROXY_AUTHORS",
    "PROXY_VERSION",
    "START_TIME",
]

__author__ = PROXY_AUTHORS

__version__ = PROXY_VERSION

################################################################################
