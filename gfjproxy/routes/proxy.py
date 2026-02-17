from traceback import print_exception

from flask import Blueprint, abort, request

from ..cooldown import get_cooldown
from ..handlers import handle_chat_message, handle_proxy_test
from ..logging import xlog, xlogtime
from ..models import JaiRequest
from ..storage import storage
from ..utils import ResponseHelper, comma_split, is_proxy_test
from ..xuid_secret import xuid_secret
from ..xuiduser import XUID, UserSettings

proxy = Blueprint("proxy", __name__)


@proxy.route("/", methods=["POST"])
@proxy.route("/chat/completions", methods=["POST"])
@proxy.route("/quiet/", methods=["POST"])
@proxy.route("/quiet/chat/completions", methods=["POST"])
def handle():
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

    api_keys = comma_split(request_auth[1])
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

    rcounter = user.get_rcounter()
    api_key_index = rcounter % len(api_keys)
    user.inc_rcounter()

    jai_req.api_key = api_keys[api_key_index]
    jai_req.key_index = api_key_index
    jai_req.key_count = len(api_keys)

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
            response = handle_proxy_test(user, jai_req, response)
        else:
            response = handle_chat_message(user, jai_req, response)
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
