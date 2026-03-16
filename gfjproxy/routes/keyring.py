import json
from hmac import digest

from flask import Blueprint, redirect, render_template, request

from .._globals import PROXY_NAME, PROXY_URL
from ..logging import xlog, xlogtime
from ..models import JaiMessage
from ..providers.gemini_cli import (
    Credentials,
    gemini_cli_generate_content_ex,
    gemini_cli_load_project_id,
    gemini_cli_refresh_credentials,
)
from ..storage import storage
from ..utils import base64url_decode, base64url_encode
from ..xuid_secret import xuid_secret

keyring = Blueprint("keyring", __name__)


@keyring.route("/keyring", methods=["GET"])
@keyring.route("/keyring/index", methods=["GET"])
@keyring.route("/keyring/index.html", methods=["GET"])
def index():
    if request.path != "/keyring":
        return redirect("/keyring", code=301)

    xlog(None, "Handling keyring index")

    return render_template(
        "keyring.html",
        title=f"Keyring - {PROXY_NAME}",
        url=PROXY_URL,
        placeholder=(
            "{\n"
            + '  "access_token": "...",\n'
            + '  "scope": "...",\n'
            + '  "token_type": "...",\n'
            + '  "id_token": "...",\n'
            + '  "expiry_date": ...,\n'
            + '  "refresh_token": "..."\n'
            + "}\n"
        ),
    )


@keyring.route("/keyring/api", methods=["POST"])
def api():
    assert storage is not None  # Make type checkers happy

    request_json = request.get_json(silent=True)
    if not request_json:  # This should never happen.
        return {"error": "Missing/invalid JSON in API call."}, 400

    type = request_json.get("credsType")
    if type not in ["gemini_cli"]:
        return {
            "error": f'Missing/invalid credentials type in API call: "{type}".'
        }, 400

    try:
        credentials = request_json.get("creds")
        if not isinstance(credentials, dict):
            return {"error": "Missing/invalid credentials in API call."}, 400
        credentials = Credentials.parse(credentials)
    except ValueError as e:
        return {"error": str(e)}, 400

    ref_time = xlogtime(None, "Keyring processing")

    ################################################################################
    # Step 1: Validate that the credentials work.
    # Basically just test that we can use Gemini CLI and make it generate a string.
    # Test that it can return the string "HELLO" similar to a JanitorAI proxy test.

    rcr = gemini_cli_refresh_credentials(None, credentials)
    if not rcr.success:
        error_code, error_message = rcr.error
        xlog(None, f"Keyring processing failed: {error_code}: {error_message}")
        return {"error": error_message}, error_code
    credentials = rcr.value

    lpidr = gemini_cli_load_project_id(None, credentials)
    if not lpidr.success:
        error_code, error_message = lpidr.error
        xlog(None, f"Keyring processing failed: {error_code}: {error_message}")
        return {"error": error_message}, error_code
    project_id = lpidr.value

    gcexr = gemini_cli_generate_content_ex(
        None,
        credentials.access_token,
        project_id,
        "gemini-3.1-flash-lite-preview",
        [JaiMessage(content="Just say HELLO")],
        {"temperature": 0},
    )
    if not gcexr.success:
        error_code, error_message = gcexr.error
        xlog(None, f"Keyring processing failed: {error_code}: {error_message}")
        return {"error": error_message}, error_code
    text = (
        gcexr.value.get("response", {})
        .get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text")
    )

    if text.strip().upper() != "HELLO":
        error_code = 502
        error_message = f"Gemini CLI gave an unexpected response: {text!r}"
        xlog(None, f"Keyring processing failed: {error_code}: {error_message}")
        return {"error": error_message}, error_code

    ################################################################################
    # Step 2: Generate an API key for the user.
    # Now that we have valid credentials that work, we can give the user a key.
    # The key is based on the proxy's URL and the credentials' subject field.
    # Both values are (hopefully) unique and stable so the key can be as well.

    try:
        jwt = credentials.id_token.split(".")
        jwt_payload = base64url_decode(jwt[1])
        jwt_payload_json = json.loads(jwt_payload)
        subject: str = jwt_payload_json["sub"]
        subject_digest = digest(xuid_secret, subject.encode("utf-8"), "sha256")
    except Exception as e:  # This should never happen.
        xlog(None, f"Keyring processing exception during key generation: {repr(e)}")
        return {"error": "Credentials have missing/invalid id_token"}, 400

    api_key = ".".join(
        [
            "gfjproxy.gemini_cli",
            base64url_encode(PROXY_URL),
            base64url_encode(subject_digest),
        ]
    )

    storage.keyring_put(api_key, json.dumps(credentials.json()))

    xlogtime(None, "Keyring processing done", ref_time)

    return {"value": api_key}, 200
