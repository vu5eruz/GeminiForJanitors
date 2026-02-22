################################################################################

# Early initialization

from ._globals import (
    BANDWIDTH_WARNING,
    CLOUDFLARED,
    COOLDOWN,
    DEVELOPMENT,
    PREFILL,
    PRESETS,
    PRODUCTION,
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
from colorama import just_fix_windows_console
from flask import Flask
from flask_cors import CORS

from .logging import hijack_loggers
from .storage import storage
from .utils import run_cloudflared
from .xuiduser import LocalUserStorage, RedisUserStorage


def create_app():
    # Proxy initialization with startup banner
    # This is made to match up with Flask's own startup banner

    print(f"GeminiForJanitors ({PROXY_VERSION})")

    just_fix_windows_console()
    hijack_loggers()

    if CLOUDFLARED is not None:
        run_cloudflared(CLOUDFLARED)

    if PRODUCTION:
        print(" * Production deployment")
    else:
        print(" * Development deployment")

    if BANDWIDTH_WARNING:
        print(f" * Bandwidth warning set at {BANDWIDTH_WARNING / 1024:.1f} GiB")
    else:
        print(" * Bandwidth warning disabled")

    if COOLDOWN:
        print(" * Using cooldown policy:", COOLDOWN)
    else:
        print(" * No cooldown policy")

    if isinstance(storage, RedisUserStorage):
        print(" * Using Redis user storage")
    elif isinstance(storage, LocalUserStorage) and DEVELOPMENT:
        print(" * Using local user storage")
    else:
        raise RuntimeError("No user storage")

    if XUID_SECRET is not None:
        print(" * Using provided XUID secret")
    elif DEVELOPMENT:
        print(" * WARNING: Using development XUID secret")
    else:
        raise RuntimeError("Missing XUID secret")

    if PRESETS:
        print(" * Using presets: " + ", ".join(PRESETS.keys()))
    else:
        print(" * WARNING: No presets loaded")

    if PREFILL:
        print(f" * Using prefill ({len(PREFILL)} characters)")
    else:
        print(" * WARNING: No prefill loaded")

    # Application initialization

    app = Flask(__name__)
    CORS(app)

    from .routes.proxy import proxy
    from .routes.system import system

    app.register_blueprint(proxy)
    app.register_blueprint(system)

    return app
