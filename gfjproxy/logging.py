"""Proxy Logging System."""

import logging
from time import monotonic, gmtime
from threading import Timer
from .xuiduser import XUID, UserSettings

################################################################################


class _CustomFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not super().filter(record):
            return False

        # Gunicorn access logger passes a dict of atoms to be formatted.
        # Werkzeug logger uses a more or less pre-formatted string.
        # Both produce logs that look like this:
        # 127.0.0.1 - - [03/Aug/2025 12:21:14] "GET / HTTP/1.1" 200 -
        # The HTTP request info is good but everything before should be stripped
        # We can hijack this and create our own format string.

        if record.name == "gunicorn.access" and isinstance(record.args, dict):
            record.msg = '"%(r)s" %(s)s %(b)s'
        elif record.name == "werkzeug" and " - - [" in record.msg:
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


class _CustomFormatter(logging.Formatter):
    converter = gmtime

    def __init__(self, filler: str | None = None):
        if filler is None:
            filler = "=" * XUID.LEN_PRETTY
        else:
            filler = filler[: XUID.LEN_PRETTY]

        super().__init__(
            fmt="%(asctime)s %(filler)s %(message)s",
            datefmt="[%Y%m%dT%H%M%SZ]",
            style="%",
            defaults={"filler": filler.rjust(XUID.LEN_PRETTY)},
        )


def _custom_handler(filler: str | None = None) -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setFormatter(_CustomFormatter(filler))
    return handler


def hijack_loggers() -> list[str]:
    """Hijack other people's loggers and make them use our custom handler.

    This is very hacky and very illegal, lol."""

    def hijack(names):
        for name in names:
            # Check whether the logger is present or not
            if name in logging.root.manager.loggerDict:
                logger = logging.getLogger(name)
                logger.addFilter(_CustomFilter())
                logger.addHandler(_custom_handler(name.split(".")[0]))

                # Remove all handlers other than our CustomFormatter
                for handler in logger.handlers:
                    if not isinstance(handler, _CustomFormatter):
                        logger.removeHandler(handler)

                xlog(None, f"Hijacked logger '{name}'")

    # Delay is completely arbitrary but seems to work fine
    hijack_thread = Timer(2.5, hijack, (["gunicorn.access", "werkzeug"],))
    hijack_thread.daemon = True
    hijack_thread.start()


################################################################################

_logger = logging.getLogger("gfjproxy")
_logger.addHandler(_custom_handler())
_logger.propagate = False
_logger.setLevel(logging.INFO)


def xlog(user: UserSettings | XUID | None, msg: str):
    extra = {}
    if user is not None:
        extra["filler"] = (
            user.xuid.pretty() if isinstance(user, UserSettings) else user.pretty()
        )
    _logger.info(msg.strip(), extra=extra)


def xlogtime(user: UserSettings | XUID | None, msg: str, prev_time=None) -> float:
    curr_time = monotonic()

    diff_time_str = ""
    if isinstance(prev_time, float):
        diff_time_str = f" ({curr_time - prev_time:.1f}s)"

    xlog(user, msg + diff_time_str)

    return curr_time


################################################################################
