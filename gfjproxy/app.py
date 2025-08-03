"""Proxy Application."""

import json
from click import echo
from colorama import just_fix_windows_console
from flask import Flask, Response, abort, request, redirect
from flask_cors import CORS
from ._globals import CLOUDFLARED, PRODUCTION, PROXY_VERSION
from .logging import hijack_loggers, xlog
from .utils import is_proxy_test, run_cloudflared
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

if CLOUDFLARED is not None:
    run_cloudflared(CLOUDFLARED)

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
    request_json = request.get_json(silent=True)
    if not request_json:  # This should never happen.
        abort(400, "Bad Request. Missing or invalid JSON.")

    # JanitorAI, as of 2025.08.03, has an idiosyncratic way of handling errors.
    # Should the proxy return an error, JanitorAI will show it to the user, but:
    # - Normal chat requests expect a regular plain text response. (nice)
    # - Proxy test requests expect a JSON object with an "error" key. (eww)
    # First things first, we have to determine if the requests is a proxy test,
    # then we can select an error handler that uses the right format.

    proxy_test = is_proxy_test(request_json)
    if proxy_test:

        def make_error(message: str, status: int) -> Response:
            return Response(
                response=json.dumps({"error": message}),
                status=status,
                content_type="application/json; charset=utf-8",
            )

    else:  # Normal chat

        def make_error(message: str, status: int) -> Response:
            return Response(
                response=message,
                status=int(status),
                content_type="text/plain; charset=utf-8",
            )

    # JanitorAI provides the user's API key through HTTP Bearer authentication.
    # Google AI cannot be used without an API key and neither can this proxy.

    request_auth = request.headers.get("authorization", "").split(" ")
    if len(request_auth) != 2 or request_auth[0] != "Bearer":
        return make_error("Unauthorized. API key required.", 401)

    api_key = request_auth[1]

    user = UserSettings(
        LocalUserStorage(),
        XUID(api_key, "The Quick Brown Fox Jumps Over The Lazy Dog"),
    )

    xlog(user, "Handling proxy")

    return make_error("Not Implemented", 501)


################################################################################
