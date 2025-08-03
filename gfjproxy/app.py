"""Proxy Application."""

from click import echo
from colorama import just_fix_windows_console
from flask import Flask, request, redirect
from flask_cors import CORS
from ._globals import PRODUCTION, PROXY_VERSION
from .logging import hijack_loggers, xlog
from .xuiduser import LocalUserStorage, UserSettings, XUID

just_fix_windows_console()
hijack_loggers()

################################################################################

# Proxy startup banner
# This is made to match up with Flask's own startup banner
# Flask uses click.echo for these messages

echo(f"GeminiForJanitors ({PROXY_VERSION})")

if PRODUCTION:
    echo(" * Production deployment")
else:
    echo(" * Development deployment")

################################################################################

app = Flask(__name__)
CORS(app)


@app.route("/", methods=["GET"])
@app.route("/index", methods=["GET"])
@app.route("/index.html", methods=["GET"])
def index():
    requested_path = request.path
    if requested_path != "/":
        return redirect("/", code=301)

    xlog(None, "Handling index")

    return "Hello, World!", 200


@app.route("/health")
@app.route("/healthz")
def health():
    return "All good.", 200


@app.route("/", methods=["POST"])
@app.route("/chat/completions", methods=["POST"])
@app.route("/quiet/", methods=["POST"])
@app.route("/quiet/chat/completions", methods=["POST"])
def proxy():
    request_auth = request.headers.get("authorization", "").split(" ")
    if len(request_auth) != 2 or request_auth[0] != "Bearer":
        return "Unauthorized. API key required.", 401

    user = UserSettings(
        LocalUserStorage(),
        XUID(request_auth[1], "The Quick Brown Fox Jumps Over The Lazy Dog"),
    )

    xlog(user, "Handling proxy")

    return "Not Implemented", 501


################################################################################
