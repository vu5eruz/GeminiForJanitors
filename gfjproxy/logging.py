"""Proxy Logging System."""

import logging
from .xuiduser import XUID

################################################################################


class CustomFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not super().filter(record):
            return False

        # Both gunicorn and werkzeug produces logs that look like:
        # 127.0.0.1 - - [03/Aug/2025 12:21:14] "GET / HTTP/1.1" 200 -
        # The HTTP request info is good but everything before should be stripped

        if " - - [" in record.msg:
            index = record.msg.find('] "')
            if index != -1:
                # Note the + 2 instead of + 3: don't cut off the opening quote
                record.msg = record.msg[index + 2 :]

        # The health endpoint is hit very frequently and it pollutes the logs.
        # While both /health and /healthz are handled, we suppress only /health.
        # /healthz is the default value on render.com and should be changed.
        # If something is hitting /healthz, then something strange is going on.

        if record.getMessage().find('"GET /health HTTP/1.1" 200') != -1:
            return False

        # All good

        return True


class CustomFormatter(logging.Formatter):
    def __init__(self, filler: str | None = None):
        if filler is None:
            filler = "=" * XUID.LEN_PRETTY
        else:
            filler = filler[: XUID.LEN_PRETTY]

        super().__init__(
            fmt="%(asctime)s %(filler)s %(message)s",
            datefmt="[%Y-%m-%d %H:%M:%S %z]",
            style="%",
            defaults={"filler": filler.rjust(XUID.LEN_PRETTY)},
        )


def custom_handler(filler: str | None = None) -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter(filler))
    return handler


def hijack_loggers() -> list[str]:
    """Hijack other people's loggers and make them use our custom handler.

    This is very hacky and very illegal, lol."""

    from time import sleep
    from threading import Thread

    def sanitize(logger):
        """Remove all handlers other than our CustomFormatter."""
        for handler in logger.handlers:
            if not isinstance(handler, CustomFormatter):
                logger.removeHandler(handler)

    def is_logger_present(name):
        return name in logging.root.manager.loggerDict

    def hijack():
        if is_logger_present("gunicorn.access"):
            logger = logging.getLogger("gunicorn.access")
            logger.addFilter(CustomFilter())
            logger.addHandler(custom_handler("gunicorn.access"))
            sanitize(logger)

        # Werkzeug's logger needs a delay otherwise hijacking has no effect
        sleep(2.5)  # Completely arbitrary value

        if is_logger_present("werkzeug"):
            logger = logging.getLogger("werkzeug")
            logger.addFilter(CustomFilter())
            logger.addHandler(custom_handler("werkzeug"))
            sanitize(logger)

    hijack_thread = Thread(target=hijack, daemon=True)
    hijack_thread.start()


################################################################################

logger = logging.getLogger("gfjproxy")
logger.addHandler(custom_handler())
logger.propagate = False
logger.setLevel(logging.INFO)


def logxuid(xuid: XUID | None, msg: str, *args, **kwargs):
    extra = {}
    if xuid is not None:
        extra["filler"] = xuid.pretty()
    logger.info(msg.strip(), *args, **kwargs, extra=extra)


################################################################################
