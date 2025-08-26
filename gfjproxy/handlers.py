"""Handlers."""

from httpx import ReadTimeout
from google import genai
from google.genai import types
from ._globals import BANNER, BANNER_VERSION, PREFILL, THINK
from .commands import CommandError
from .models import JaiRequest
from .logging import xlog
from .xuiduser import LocalUserStorage, UserSettings


REQUEST_TIMEOUT_IN_SECONDS: float = 60

################################################################################


def _get_feedback(response: types.GenerateContentResponse) -> str | None:
    """Extracts a human-readable message from a failed GenerateContentResponse.

    Returns None if no message could be extracted."""

    if prompt_feedback := response.prompt_feedback:
        if prompt_feedback.block_reason_message:
            return str(prompt_feedback.block_reason_message)
        if isinstance(prompt_feedback.block_reason, types.BlockedReason):
            return prompt_feedback.block_reason.name

    if candidates := response.candidates:
        if (
            isinstance(candidates, list)
            and len(candidates) >= 1
            and isinstance(candidates[0], types.Candidate)
            and isinstance(candidates[0].finish_reason, types.FinishReason)
        ):
            return candidates[0].finish_reason.name

    return None


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
                    + (" (for this message only)." if not user.use_nobot else "."),
                )
            else:
                contents.append(types.ModelContent({"text": msg.content}))
            continue

        if msg.role == "assistant":
            contents.append(types.ModelContent({"text": msg.content}))
        else:
            contents.append(types.UserContent({"text": msg.content}))

    if jai_req.use_think or user.use_think:
        xlog(
            user,
            "Adding thinking to chat"
            + (" (for this message only)." if not user.use_think else "."),
        )

        contents.append(types.ModelContent({"text": THINK}))

        used_think = True
    else:
        used_think = False

    if jai_req.use_preset:
        xlog(user, "Adding preset to chat")

        contents.append(types.ModelContent({"text": jai_req.use_preset}))

    if jai_req.use_prefill or user.use_prefill:
        xlog(
            user,
            "Adding prefill to chat"
            + (" (for this message only)." if not user.use_prefill else "."),
        )

        contents.append(types.ModelContent({"text": PREFILL}))

        used_prefill = True
    else:
        used_prefill = False

    if used_think:
        contents.append(
            types.ModelContent(
                {
                    "text": "Remember to use <think>...</think> for your reasoning and <response>...</response> for your roleplay content."
                }
            )
        )
        contents.append(types.ModelContent({"text": "<think>\n➛ Okay! Understood."}))

    config = {
        "http_options": types.HttpOptions(
            timeout=REQUEST_TIMEOUT_IN_SECONDS * 1_000  # milliseconds
        ),
        "temperature": jai_req.temperature,
        "top_k": 50,
        "top_p": 0.95,
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

    # At some point in the future, we might want to add a //maxtokens command
    # to turn this settings on and off. Meanwhile, this is out.
    #
    # if jai_req.max_tokens > 0:
    #     config["max_output_tokens"] = jai_req.max_tokens

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
        xlog(user, repr(e))  # Temporarily log these errors to collect them

        return e.message, e.code
    except genai.errors.ServerError as e:
        if e.status == "UNAVAILABLE":
            # 503 UNAVAILABLE "The model is overloaded. Please try again later."
            return e.message, e.code

        if e.status == "INTERNAL":
            # 500 INTERNAL "An internal error has occurred."
            # The actual message is longer and not really relevant to the users.
            # Skip logging these errors and return our own message instead.
            return "Google AI had an internal error. Try again later.", 503

        xlog(user, repr(e))  # Log these fellas for they are anomalous
        return "Google AI had an internal error.", 502
    except Exception as e:
        xlog(user, repr(e))  # These are R E A L L Y anomalous
        return "Unhanded exception from Google AI.", 502

    if not (text := result.text):
        # Rejection

        reason = _get_feedback(result)
        if not reason:
            xlog(user, f"No result text: {result}")
            reason = "unknown reason"

        message = f"Response blocked/empty due to {reason}."

        if reason == "MAX_TOKENS":
            message += '\nTry increasing "Max tokens" in your Generation Settings or set it to zero to disable it.'
        elif not used_prefill and not used_think:
            message += "\nTry using `//prefill this` and/or `//think this`"

        return message, 502

    if used_think:
        # Try first to remove any thinking and then try to recover the response
        # Make sure to remove the tags as well

        t_open = text.find("<think>")  # len = 7
        t_close = text.find("</think>")  # len = 8

        if -1 == t_open == t_close:
            xlog(user, "No thinking tags found")
        elif -1 < t_open < t_close:
            xlog(user, f"Removing thinking (case #1) {t_open} to {t_close + 8}")
            text = text[:t_open] + text[t_close + 8 :]
        elif -1 < t_close:
            xlog(user, f"Removing thinking (case #2) up until {t_close + 8}")
            text = text[t_close + 8 :]
        else:
            xlog(user, "Removing thinking failure")

        r_open = text.find("<response>")  # len = 10
        r_close = text.find("</response>")  # len = 11

        if -1 == r_open == r_close:
            xlog(user, "No response tags found")
        elif -1 < r_open < r_close:
            xlog(user, f"Parsing response (case #1) {r_open + 10} to {r_close}")
            text = text[r_open + 10 : r_close]
        elif -1 < r_open:
            xlog(user, f"Parsing response (case #2) {r_open + 10} onwards")
            text = text[r_open + 10 :]
        else:
            xlog(user, "Parsing response failure")

    return (result, text), 200


################################################################################


def handle_proxy_test(client: genai.Client, user, jai_req, response):
    """Proxy test handler.

    The sole purpose of this is to test out the user's API key and model."""

    xlog(user, f"Handling proxy test ({jai_req.model}) ...")

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

    result, text = result

    return response.add_message(text)


def handle_chat_message(client: genai.Client, user, jai_req, response):
    """Chat message handler.

    This handles when the user sends a simple chat message to the bot."""

    if jai_req.messages[-1].content.startswith("Rewrite/Enhance this message: "):
        xlog(user, f"Handling enhance message ({jai_req.model}) ...")
    else:
        xlog(user, f"Handling chat message ({jai_req.model}) ...")

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

    result, text = result

    response.add_message(text)

    if isinstance(result.usage_metadata, types.GenerateContentResponseUsageMetadata):
        xlog(user, f" - Prompt   tokens {result.usage_metadata.prompt_token_count}")
        xlog(user, f" - Response tokens {result.usage_metadata.candidates_token_count}")
        xlog(user, f" - Thinking tokens {result.usage_metadata.thoughts_token_count}")
        xlog(user, f" - Total    tokens {result.usage_metadata.total_token_count}")
    else:
        xlog(user, " - No usage metadata")

    if not jai_req.quiet and user.do_show_banner(BANNER_VERSION):
        xlog(
            user, f"Showing{' new ' if not user.exists else ' '}user the latest banner"
        )
        response.add_message(BANNER)

    return response


################################################################################
