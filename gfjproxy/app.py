################################################################################

# Early initialization

from ._globals import (
    BANDWIDTH_WARNING,
    CLOUDFLARED,
    COOLDOWN,
    PRODUCTION,
    PROXY_BRANCH,
    PROXY_NAME,
    PROXY_VERSION,
    XUID_SECRET,
)

if PRODUCTION:
    # Production runs on gunicorn with gevent.
    # Make sure to prevent issues with ssl monkey-patching.
    from gevent import monkey

    monkey.patch_all()

################################################################################

# ruff: noqa: E402
import gc

from colorama import just_fix_windows_console
from flask import Flask
from flask_cors import CORS
from psutil import Process

from .logging import hijack_loggers, xlog
from .storage import storage
from .utils import run_cloudflared
from .xuiduser import RedisUserStorage

_process = Process()


def _teardown(exception):
    gc.collect()

    if not PRODUCTION:
        xlog(None, f"Memory {_process.memory_info().rss / 1048576:.1f} MiB")


def create_app():
    just_fix_windows_console()
    hijack_loggers()

    if PRODUCTION:
        if not isinstance(storage, RedisUserStorage):
            raise RuntimeError("Production user storage must be Redis")
        if not XUID_SECRET:
            raise RuntimeError("Production must have set XUID secret")

    if CLOUDFLARED is not None:
        run_cloudflared(CLOUDFLARED)

    xlog(
        None,
        " ".join(
            [
                f"{PROXY_NAME} ({PROXY_VERSION} {PROXY_BRANCH})",
                "production" if PRODUCTION else "development",
                f"bwarning={BANDWIDTH_WARNING / 1024:.1f}GiB",
                f"cpolicy={COOLDOWN!r}",
                f"ustorage={'redis' if isinstance(storage, RedisUserStorage) else 'local'}",
                f"xuid={'set' if XUID_SECRET else 'unset'}",
            ]
        ),
    )

    # Application initialization

    app = Flask(__name__)
    CORS(app)

    from .routes.keyring import keyring
    from .routes.proxy import proxy
    from .routes.system import system

    app.register_blueprint(keyring)
    app.register_blueprint(proxy)
    app.register_blueprint(system)

    app.teardown_request(_teardown)

    return app
