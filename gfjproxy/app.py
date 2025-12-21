"""Proxy Application."""

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
    PROXY_ADMIN,
    PROXY_NAME,
    PROXY_URL,
    PROXY_VERSION,
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
from secrets import token_bytes
from time import perf_counter
from traceback import print_exception

from colorama import just_fix_windows_console
from flask import Flask, abort, redirect, render_template, request, send_from_directory
from flask_cors import CORS
from google import genai

from .bandwidth import bandwidth_usage
from .cooldown import cooldown_policy, get_cooldown
from .handlers import handle_chat_message, handle_proxy_test
from .logging import hijack_loggers, xlog, xlogtime
from .models import JaiRequest
from .start_time import START_TIME
from .storage import storage
from .utils import ResponseHelper, is_proxy_test, run_cloudflared
from .xuiduser import XUID, LocalUserStorage, RedisUserStorage, UserSettings

just_fix_windows_console()
hijack_loggers()

################################################################################

# Late initialization

if CLOUDFLARED is not None:
    run_cloudflared(CLOUDFLARED)


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
    assert storage is not None  # Make type checkers happy

    if request.path != "/":
        return redirect("/", code=301)

    xlog(None, "Handling index")

    return render_template(
        "index.html",
        admin=PROXY_ADMIN,
        announcement=storage.announcement,
        title=PROXY_NAME,
        version=PROXY_VERSION,
    )


@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.ico")


@app.route("/health")
@app.route("/healthz")
def health():
    keyspace = -1
    if isinstance(storage, RedisUserStorage):
        keyspace = storage._client.info("keyspace").get("db0", {}).get("keys", -1)

    usage = bandwidth_usage()

    health = {
        "admin": PROXY_ADMIN,
        "bandwidth": usage.total,
        "cooldown": get_cooldown(usage),
        "cpolicy": str(cooldown_policy),
        "keyspace": keyspace,
        "uptime": int(perf_counter() - START_TIME),
        "version": PROXY_VERSION,
    }

    if request.headers.get("accept", "").split(",")[0] == "text/html":
        return render_template(
            "health.html",
            health=health,
            title=PROXY_NAME,
            url=PROXY_URL,
        )

    # Return health data as JSON
    return health, 200


@app.route("/", methods=["POST"])
@app.route("/chat/completions", methods=["POST"])
@app.route("/quiet/", methods=["POST"])
@app.route("/quiet/chat/completions", methods=["POST"])
def proxy():
    assert storage is not None  # Make type checkers happy

    request_json = request.get_json(silent=True)
    if not request_json:  # This should never happen.
        abort(400, "Bad Request. Missing or invalid JSON.")
        return  # Some type checkers don't realize abort exits the function

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

    if (seconds := user.last_seen()) and (cooldown := get_cooldown()):
        if (delay := cooldown - seconds) > 0:
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
        elif proxy_test:
            response = handle_proxy_test(client, user, jai_req, response)
        else:
            response = handle_chat_message(client, user, jai_req, response)
    except Exception as e:
        response.add_error("Internal Proxy Error", 500)
        print_exception(e)

    if 200 <= response.status <= 299:
        xlogtime(user, "Processing succeeded", ref_time)

        if not proxy_test and (announcement := storage.announcement):
            response.add_proxy_message(f"***\n{announcement}\n***")
    else:
        messages = response.message.split("\n")
        xlogtime(user, f"Processing failed: {messages[0]}", ref_time)
        for message in messages[1:]:
            xlog(user, f"> {message}")

    if user.valid:
        user.save()
    else:
        xlog(user, "Invalid user not saved")

    storage.unlock(xuid)

    return response.build()


################################################################################


def secret_required(f):
    from functools import wraps

    @wraps(f)
    def secret_required_wrapper():
        if request.args.get("secret") != XUID_SECRET:
            return {
                "success": False,
                "error": "secret required.",
            }, 403

        return f()

    return secret_required_wrapper


@app.route("/admin/dump-all", methods=["GET"])
@secret_required
def admin_dump_all():
    if not isinstance(storage, RedisUserStorage):
        return {
            "success": False,
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
        "success": True,
        "locks": locks,
        "dump": dump,
    }


################################################################################
