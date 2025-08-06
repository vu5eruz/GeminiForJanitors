"""Handlers."""

from httpx import ReadTimeout
from google import genai
from google.genai import types
from ._globals import BANNER, BANNER_VERSION, PREFILL
from .commands import CommandError
from .models import JaiRequest
from .logging import xlog
from .xuiduser import LocalUserStorage, UserSettings


REQUEST_TIMEOUT_IN_SECONDS: float = 60

################################################################################


def _gen_content(
    client: genai.Client, user: UserSettings, jai_req: JaiRequest, overrides=dict()
):
    """Wrapper around client.models.generate_content.

    Returns (GenerateContentResponse, 200) on success.
    On any errors, returns a string and a code other than one."""

    contents = []

    for msg in jai_req.messages:
        if msg.role == "system":
            if jai_req.use_nobot or user.use_nobot:
                xlog(
                    user,
                    "Omitting bot description from system prompt"
                    + " (for this message only)."
                    if not user.use_nobot
                    else ".",
                )
            else:
                contents.append(types.ModelContent({"text": msg.content}))
            continue

        if msg.role == "assistant":
            contents.append(types.ModelContent({"text": msg.content}))
        else:
            contents.append(types.UserContent({"text": msg.content}))

    if jai_req.use_preset:
        xlog(user, "Adding preset to chat")

        contents.append(types.ModelContent({"text": jai_req.use_preset}))

    if jai_req.use_prefill or user.use_prefill:
        xlog(
            user,
            "Adding prefill to chat" + " (for this message only)."
            if not user.use_prefill
            else ".",
        )

        contents.append(types.ModelContent({"text": PREFILL}))

    config = {
        "http_options": types.HttpOptions(
            timeout=REQUEST_TIMEOUT_IN_SECONDS * 1_000  # milliseconds
        ),
        "temperature": jai_req.temperature,
        "top_k": 50,
        "top_p": 0.95,
        "candidate_count": 1,
        "safety_settings": [
            types.SafetySetting(
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            ),
            types.SafetySetting(
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            ),
            types.SafetySetting(
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            ),
            types.SafetySetting(
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            ),
            types.SafetySetting(
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
                category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
            ),
        ],
    }

    if jai_req.max_tokens > 0:
        config["max_output_tokens"] = jai_req.max_tokens

    for key, value in overrides.items():
        if value is None and key in config:
            del config[key]
        else:
            config[key] = value

    try:
        result = client.models.generate_content(
            model=jai_req.model, contents=contents, config=config
        )
    except ReadTimeout:
        return "Gateway Timeout", 504
    except genai.errors.ClientError as e:
        return e.message, e.code
    except genai.errors.ServerError as e:
        xlog(user, repr(e))  # Log these fellas for they are anomalous
        return "Google AI had an internal error.", 502
    except Exception as e:
        xlog(user, repr(e))  # These are R E A L L Y anomalous
        return "Unhanded exception from Google AI.", 502

    if result.candidates is None:
        if result.prompt_feedback is None:
            return "Google AI returned no response", 502

        reason = "unknown reason"
        if isinstance(result.prompt_feedback.block_reason, types.BlockedReason):
            reason = result.prompt_feedback.block_reason.name
        return f"Response blocked due to {reason}", 502

    return result, 200


################################################################################


def handle_proxy_test(client: genai.Client, user, jai_req, response):
    """Proxy test handler.

    The sole purpose of this is to test out the user's API key and model."""

    xlog(user, "Handling proxy test ...")

    # We need to provide _gen_content with empty user settings to prevent any of
    # the user's actual settings from altering the request at all. Pass on the
    # user's XUID so we get correct logging.
    #
    # We need to override max_output_tokens because jai_req.max_tokens during a
    # proxy test is set too low and guarantees the model to fail. Unbound the
    # token limit so that if everything is good then we can get a good response.

    result, status = _gen_content(
        client,
        UserSettings(LocalUserStorage(), user.xuid),
        jai_req,
        {"max_output_tokens": None},
    )

    if status != 200:
        return response.add_error(result, status)

    return response.add_message(result.text)


def handle_chat_message(client: genai.Client, user, jai_req, response):
    """Chat message handler.

    This handles when the user sends a simple chat message to the bot."""

    if jai_req.messages[-1].content.startswith("Rewrite/Enhance this message: "):
        xlog(user, "Handling enhance message ...")
    else:
        xlog(user, "Handling chat message ...")

    for command in jai_req.messages[-1].commands:
        xlog(user, f"//{command.name} {command.args}")

        try:
            response = command(user, jai_req, response)
        except CommandError as e:
            message = f"Error: {e} (Command has been ignored.)"
            response.add_proxy_message(message)
            xlog(user, message)

    result, status = _gen_content(client, user, jai_req)

    if status != 200:
        return response.add_error(result, status)

    response.add_message(result.text)

    if isinstance(result.usage_metadata, types.GenerateContentResponseUsageMetadata):
        xlog(user, f" - Prompt   tokens {result.usage_metadata.prompt_token_count}")
        xlog(user, f" - Response tokens {result.usage_metadata.candidates_token_count}")
        xlog(user, f" - Thinking tokens {result.usage_metadata.thoughts_token_count}")
        xlog(user, f" - Total    tokens {result.usage_metadata.total_token_count}")
    else:
        xlog(user, " - No usage metadata")

    if not jai_req.quiet and user.do_show_banner(BANNER_VERSION):
        xlog(user, "Showing user the latest banner")
        response.add_message(BANNER)

    return response


################################################################################
