"""Proxy Application."""

from click import echo
from colorama import just_fix_windows_console
from flask import Flask, abort, request, redirect
from flask_cors import CORS
from google import genai
from secrets import token_bytes
from traceback import print_exception
from ._globals import (
    CLOUDFLARED,
    MODELS,
    DEVELOPMENT,
    PREFILL,
    PRODUCTION,
    PROXY_VERSION,
    REDIS_URL,
    XUID_SECRET,
)
from .handlers import handle_chat_message, handle_proxy_test
from .models import JaiRequest
from .logging import hijack_loggers, xlog, xlogtime
from .utils import ResponseHelper, is_proxy_test, run_cloudflared
from .xuiduser import LocalUserStorage, RedisUserStorage, UserSettings, XUID

just_fix_windows_console()
hijack_loggers()

################################################################################

# Proxy initialization with startup banner
# This is made to match up with Flask's own startup banner
# Flask uses click.echo for these messages

echo(f"GeminiForJanitors ({PROXY_VERSION})")

if PRODUCTION:
    echo(" * Production deployment")
else:
    echo(" * Development deployment")

if CLOUDFLARED is not None:
    run_cloudflared(CLOUDFLARED)

if REDIS_URL is not None:
    storage = RedisUserStorage(REDIS_URL)
    echo(" * Using Redis user storage")
elif DEVELOPMENT:
    storage = LocalUserStorage()
    echo(" * WARNING: Using local user storage")
else:
    echo(" * ERROR: No user storage")
    exit(1)

try:
    with open(PREFILL, encoding="utf-8") as prefill:
        prefill = prefill.read()
    echo(f" * Loaded prefill from file {PREFILL} ({len(prefill)} characters)")
except FileNotFoundError:
    echo(f" * ERROR: Prefill file {PREFILL} not found.")
    prefill = ""

if XUID_SECRET is not None:
    echo(" * Using provided XUID secret")
    xuid_secret = XUID_SECRET.encode("utf-8")
elif DEVELOPMENT:
    echo(" * WARNING: Using development XUID secret")
    xuid_secret = token_bytes(32)
else:
    echo(" * ERROR: Missing XUID secret")
    exit(1)


################################################################################

app = application = Flask(__name__)
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

    request_path = request.path

    proxy_test = is_proxy_test(request_json)

    response = ResponseHelper(wrap_errors=proxy_test)

    # JanitorAI provides the user's API key through HTTP Bearer authentication.
    # Google AI cannot be used without an API key and neither can this proxy.

    request_auth = request.headers.get("authorization", "").split(" ")
    if len(request_auth) != 2 or request_auth[0] != "Bearer":
        return response.build_error("Unauthorized. API key required.", 401)

    api_key = request_auth[1]
    user = UserSettings(storage, XUID(api_key, xuid_secret))

    # Handle user's request

    jai_req = JaiRequest.parse(request_json)
    jai_req.quiet = "/quiet/" in request_path

    client = genai.Client(api_key=api_key)

    ref_time = xlogtime(
        user, f"Processing {request_path} (User {user.last_seen_msg()})"
    )

    try:
        if not jai_req.model:
            response.add_error("Please specify a Gemini 2.5 model.", 400)
        elif jai_req.model not in MODELS:
            response.add_error(
                f"Invalid or unsupported Gemini 2.5 model: {jai_req.model}", 400
            )
        elif jai_req.stream:
            response.add_error("Text streaming is not supported.", 400)
        elif proxy_test:
            response = handle_proxy_test(client, user, jai_req, response)
        else:
            response = handle_chat_message(client, user, jai_req, response)
    except Exception as e:
        response.add_error("Internal Proxy Error", 500)
        print_exception(e)

    if 200 <= response.status <= 299:
        xlogtime(user, "Processing succeeded", ref_time)
    else:
        xlogtime(
            user,
            f"Processing failed: {response.message}",
            ref_time,
        )

    user.save()

    return response.build()


################################################################################
