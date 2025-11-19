"""Proxy Application."""

################################################################################

# Early initialization

from ._globals import (
    CLOUDFLARED,
    DEVELOPMENT,
    MODELS,
    PREFILL,
    PRESETS,
    PRODUCTION,
    PROXY_ADMIN,
    PROXY_COOLDOWN,
    PROXY_NAME,
    PROXY_VERSION,
    REDIS_URL,
    XUID_SECRET,
)

# Proxy initialization with startup banner
# This is made to match up with Flask's own startup banner

print(f"GeminiForJanitors ({PROXY_VERSION})")

if PRODUCTION:
    print(" * Production deployment")

    # Production runs on gunicorn with gevent.
    # Make sure to prevent issues with ssl monkey-patching.

    from gevent import monkey

    monkey.patch_all()
else:
    print(" * Development deployment")

################################################################################

# ruff: noqa: E402
from colorama import just_fix_windows_console
from flask import Flask, abort, request, redirect, render_template, send_from_directory
from flask_cors import CORS
from google import genai
from secrets import token_bytes
from traceback import print_exception
from .handlers import handle_chat_message, handle_proxy_test
from .models import JaiRequest
from .logging import hijack_loggers, xlog, xlogtime
from .utils import ResponseHelper, is_proxy_test, run_cloudflared
from .xuiduser import LocalUserStorage, RedisUserStorage, UserSettings, XUID

just_fix_windows_console()
hijack_loggers()

################################################################################

# Late initialization

if CLOUDFLARED is not None:
    run_cloudflared(CLOUDFLARED)

if REDIS_URL is not None:
    storage = RedisUserStorage(REDIS_URL)
    print(" * Using Redis user storage")
elif DEVELOPMENT:
    storage = LocalUserStorage()
    print(" * WARNING: Using local user storage")
else:
    print(" * ERROR: No user storage")
    exit(1)

if XUID_SECRET is not None:
    print(" * Using provided XUID secret")
    xuid_secret = XUID_SECRET.encode("utf-8")
elif DEVELOPMENT:
    print(" * WARNING: Using development XUID secret")
    xuid_secret = token_bytes(32)
else:
    print(" * ERROR: Missing XUID secret")
    exit(1)

if PRESETS:
    print(" * Using presets: " + ", ".join(PRESETS.keys()))
else:
    print(" * WARNING: No presets loaded")

if PREFILL:
    print(f" * Using prefill ({len(PREFILL)} characters)")
else:
    print(" * WARNING: No prefill loaded")

################################################################################

app = application = Flask(__name__)
CORS(app)


@app.route("/", methods=["GET"])
@app.route("/index", methods=["GET"])
@app.route("/index.html", methods=["GET"])
def index():
    if request.path != "/":
        return redirect("/", code=301)

    xlog(None, "Handling index")

    return render_template(
        "index.html", admin=PROXY_ADMIN, title=PROXY_NAME, version=PROXY_VERSION
    )


@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.ico")


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

    jai_req = JaiRequest.parse(request_json)
    jai_req.quiet = "/quiet/" in request_path

    proxy_test = is_proxy_test(request_json)

    response = ResponseHelper(use_stream=jai_req.stream, wrap_errors=proxy_test)

    # JanitorAI provides the user's API key through HTTP Bearer authentication.
    # Google AI cannot be used without an API key and neither can this proxy.

    request_auth = request.headers.get("authorization", "").split(" ", maxsplit=1)
    if len(request_auth) != 2 or request_auth[0].lower() != "bearer":
        return response.build_error("Unauthorized. API key required.", 401)

    api_keys = [k.strip() for k in request_auth[1].split(",")]
    xuid = XUID(api_keys[0], xuid_secret)

    if not storage.lock(xuid):
        xlog(xuid, "User attempted concurrent use")
        return response.build_error(
            "Concurrent use is not allowed. Please wait a moment.", 403
        )

    user = UserSettings(storage, xuid)

    # Cheap and easy rate limiting

    if seconds := user.last_seen():
        if seconds < PROXY_COOLDOWN:
            delay = PROXY_COOLDOWN - seconds
            xlog(user, f"User told to wait {delay} seconds")
            storage.unlock(xuid)
            return response.build_error(f"Please wait {delay} seconds.", 429)

    # Handle user's request

    api_key_index = user.get_rcounter() % len(api_keys)

    user.inc_rcounter()

    client = genai.Client(api_key=api_keys[api_key_index])

    log_details = [
        f"User {user.last_seen_msg()}",
        f"Request #{user.get_rcounter()}",
    ]

    if len(api_keys) > 1:
        log_details.append(f"Key {api_key_index + 1}/{len(api_keys)}")

    ref_time = xlogtime(
        user,
        f"Processing {'stream ' if jai_req.stream else ''}{request_path} ({', '.join(log_details)})",
    )

    try:
        if not jai_req.model:
            response.add_error("Please specify a model.", 400)
        elif jai_req.model not in MODELS:
            response.add_error(f"Invalid/unsupported model: {jai_req.model}", 400)
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
        messages = response.message.split("\n")
        xlogtime(user, f"Processing failed: {messages[0]}", ref_time)
        for message in messages[1:]:
            xlog(user, f"> {message}")

    user.save()

    storage.unlock(xuid)

    return response.build()


################################################################################


@app.route("/admin/dump-all", methods=["GET"])
def admin():
    if request.args.get("secret") != XUID_SECRET:
        return {
            "error": "secret required.",
        }, 403

    if not isinstance(storage, RedisUserStorage):
        return {
            "error": "storage is not redis.",
        }, 403

    r = storage._client

    locks = list()
    dump = dict()
    for key in map(bytes.decode, r.scan_iter(match="*", count=100)):
        if key.endswith(":lock"):
            locks.append(key)
        else:
            dump[key] = ...

    from itertools import batched
    from json import loads

    for batch in batched(dump.keys(), 100):
        for key, value in zip(batch, map(loads, r.mget(batch))):
            dump[key] = value

    return {
        "locks": locks,
        "dump": dump,
    }


################################################################################
