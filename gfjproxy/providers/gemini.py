from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx2

from ..http_client import http_client
from ..logging import xlog
from ..models import JaiMessage, JaiResult, JaiResultMetadata, JaiResultTokenUsage
from ..statistics import track_stats
from ..xuiduser import XUID

################################################################################

# Thinking effort used for every model that accepts a thinking level.
THINKING_LEVEL = "MEDIUM"

# Gemini 3 and newer: sampling settings (temperature, top_k, top_p) are deprecated
# and thinking depth is set with a thinking level instead of a token budget.
_THINKING_LEVEL_MODELS = ("gemini-3", "gemini-4")

# Models in that family that are not documented as accepting MEDIUM.
# They are left on their own default thinking level.
_NO_MEDIUM_MODELS = ("gemini-3.1-flash-lite",)

SAFETY_SETTINGS: list[dict[str, str]] = [
    {"threshold": "BLOCK_NONE", "category": category}
    for category in (
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_JAILBREAK",
    )
]


def uses_thinking_level(model: str) -> bool:
    """True for Gemini 3+ models, which ignore sampling settings and take a thinking level."""
    return model.startswith(_THINKING_LEVEL_MODELS)


def build_generation_config(
    model: str, settings: dict[str, Any] | None
) -> dict[str, Any]:
    """Converts proxy settings into a Gemini generationConfig.

    Shared by the Google AI and Gemini CLI providers."""
    generation_config: dict[str, Any] = {}
    modern = uses_thinking_level(model)

    for key, value in (settings or {}).items():
        if key == "max_tokens":
            generation_config["maxOutputTokens"] = value
        elif key == "frequency_penalty":
            generation_config["frequencyPenalty"] = value
        elif key == "repetition_penalty":
            generation_config["presencePenalty"] = value
        elif modern:
            continue  # Sampling settings are deprecated on Gemini 3+
        elif key == "temperature":
            generation_config["temperature"] = value
        elif key == "top_k":
            generation_config["topK"] = value
        elif key == "top_p":
            generation_config["topP"] = value

    if modern and not model.startswith(_NO_MEDIUM_MODELS):
        generation_config["thinkingConfig"] = {"thinkingLevel": THINKING_LEVEL}

    return generation_config


################################################################################


def _resolve_link(user: XUID, link: str) -> str:
    result = link

    try:
        if link.startswith(
            "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
        ):
            response = http_client.get(link)
            if response.status_code != 302:  # Found
                response.raise_for_status()
            if location := response.headers.get("Location"):
                result = location
    except httpx2.HTTPError as e:
        xlog(user, f"Could not resolve link:\n{e!r}")

    if result != link:
        xlog(user, "Link resolved")
    else:
        xlog(user, "Link not resolved")

    return result


def _resolve_links(user: XUID, links: list[str]) -> list[str]:
    """Resolves grounding links concurrently, keeping order and dropping duplicates.

    Each lookup can take up to the client's timeout, so resolving them one by one
    could add many seconds to a search-enabled reply."""
    unique = list(dict.fromkeys(links))
    if len(unique) <= 1:
        return [_resolve_link(user, link) for link in unique]
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        return list(pool.map(lambda link: _resolve_link(user, link), unique))


def _get_finish_reason_feedback(response: dict[str, Any]) -> str | None:
    """Extracts a human-readable message from a failed GenerateContentResponse dictionary.

    Returns None if no message could be extracted."""

    prompt_feedback = response.get("promptFeedback")
    if isinstance(prompt_feedback, dict):
        if block_reason_message := prompt_feedback.get("blockReasonMessage"):
            return str(block_reason_message)
        if block_reason := prompt_feedback.get("blockReason"):
            return str(block_reason)

    try:
        return response["candidates"][0]["finishReason"]
    except (KeyError, IndexError, TypeError):
        return None


def _get_quota_violation_feedback(qid: str) -> str | None:
    """Converts a quota ID into a human-readable message.

    Returns None if an unknown quota ID is given."""

    if qid.startswith(
        (
            "GenerateContentInputTokensPerModelPerMinute",
            "GenerateContentPaidTierInputTokensPerModelPerMinute",
        )
    ):
        return "Input Tokens per Minute quota exceeded."

    if qid.startswith("GenerateContentInputTokensPerModelPerDay"):
        return "Input Tokens per Day quota exceeded."

    if qid.startswith("GenerateRequestsPerMinutePerProjectPerModel"):
        return "Requests per Minute quota exceeded."

    if qid.startswith("GenerateRequestsPerDayPerProjectPerModel"):
        return "Requests per Day quota exceeded."

    return None


def gemini_generate_content(
    user: XUID,
    api_key: str,
    model: str,
    messages: list[JaiMessage],
    settings: dict[str, Any] | None = None,
) -> JaiResult:
    """Wrapper around Google AI's Gemini.

    User paramater is only used for logging. Generation settings must all be passed inside the
    settings parameter."""

    gemini_request: dict[str, Any] = {
        "safetySettings": SAFETY_SETTINGS,
        "generationConfig": build_generation_config(model, settings),
        "contents": [
            {
                "role": "user" if msg.role == "user" else "model",
                "parts": [{"text": msg.content}],
            }
            for msg in messages
        ],
    }
    if (settings or {}).get("search"):
        gemini_request["tools"] = [{"googleSearch": {}}]

    try:
        response = http_client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key},
            json=gemini_request,
            timeout=90,
        )
        response.raise_for_status()
        gemini_result = response.json()
    except httpx2.TimeoutException:
        track_stats("g.time_out")
        return JaiResult(504, "Gateway Timeout")
    except httpx2.HTTPStatusError as e:
        message = "Error from Google AI"
        metadata = JaiResultMetadata()
        extras = ""

        if e.response.is_client_error:
            stats_key = "g.failed.client"
        elif e.response.is_server_error:
            stats_key = "g.failed.server"
        else:
            stats_key = "g.failed.unknown"

        try:
            error = e.response.json()
        except ValueError:  # HTML or plain-text error page
            error = None
        if not isinstance(error, dict):
            error = None

        if error:
            if "error" in error:
                error = error["error"]

            error_code = error.get("code", e.response.status_code)
            error_message = error.get("message", "")
            error_status = error.get("status", "")
            error_details = error.get("details", [])

            if error_status == "NOT_FOUND":
                stats_key += ".not_found"
                if error_message.startswith("models/"):
                    stats_key += ".model"
                    error_message = f"Invalid/unsupported model '{model}'"
                elif "no longer available" in error_message:
                    stats_key += ".unavailable"
                    error_message = f"Model '{model}' is no longer available"
            elif error_status == "UNAUTHENTICATED":
                stats_key += ".unauthenticated"
                if "invalid authentication credentials" in error_message:
                    stats_key += ".api_key"
                    error_message = (
                        "Request had invalid authentication credentials.\n"
                        "Your API key is probably not valid."
                    )
                    metadata.api_key_valid = False
            elif error_status == "INVALID_ARGUMENT":
                stats_key += ".invalid"
                if "API key not valid" in error_message:
                    stats_key += ".api_key"
                    metadata.api_key_valid = False
                elif "ending with a model turn" in error_message:
                    stats_key += ".turns"
                    extras = "Disable your prefills or use `//fixturns on`."
            elif error_status == "PERMISSION_DENIED":
                stats_key += ".denied"
                for detail in error_details:
                    if (
                        not isinstance(detail, dict)
                        or detail.get("@type")
                        != "type.googleapis.com/google.rpc.ErrorInfo"
                        or not (reason := detail.get("reason"))
                    ):
                        continue
                    if reason == "SERVICE_DISABLED":
                        stats_key += ".disabled"
                        error_message = "Generative Language API needs to be enabled"
                        break
                    if reason == "CONSUMER_SUSPENDED":
                        stats_key += ".suspended"
                        error_message = "Customer suspended. You might be banned."
                        break
                else:
                    stats_key += ".unknown"
            elif error_status == "RESOURCE_EXHAUSTED":
                stats_key += ".quota"
                for detail in error_details:
                    if (
                        not isinstance(detail, dict)
                        or detail.get("@type")
                        != "type.googleapis.com/google.rpc.QuotaFailure"
                    ):
                        continue
                    quota_ids = (
                        str(v.get("quotaId", ""))
                        for v in detail.get("violations", [])
                        if isinstance(v, dict)
                    )
                    for qid in quota_ids:
                        if feedback := _get_quota_violation_feedback(qid):
                            stats_key += f".{qid}"
                            error_message = feedback
                            break
                    else:
                        stats_key += ".unknown"
                        break

            message += f" ({error_code}): {error_status}\n{error_message}"
        elif error_text := e.response.text:
            xlog(user, f"{message}: {e.response.text!r}")

            message += (
                f" ({e.response.status_code}):\n{error_text[:100]}"
                f"{'...' if len(error_text) > 100 else ''}"
            )

        track_stats(stats_key)
        return JaiResult(
            e.response.status_code, message, extras=extras, metadata=metadata
        )
    except Exception as e:  # ruff: ignore[BLE001]
        xlog(user, repr(e))  # These are R E A L L Y anomalous
        track_stats("g.failed.unknown")
        return JaiResult(502, "Unhanded exception from Google AI.")

    text = ""
    extras = ""
    metadata = JaiResultMetadata()

    if (candidates := gemini_result.get("candidates")) and isinstance(candidates, list):
        if len(candidates) > 1:
            xlog(user, "Warning: more than one candidate found in response")
        candidate = candidates[0]
        if isinstance(candidate, dict):
            if (
                (content := candidate.get("content"))
                and isinstance(content, dict)
                and (parts := content.get("parts"))
                and isinstance(parts, list)
            ):
                text = "".join(
                    part_text
                    for part in parts
                    if isinstance(part, dict)
                    and isinstance((part_text := part.get("text")), str)
                    and not part.get("thought", False)
                )

            if gm := candidate.get("groundingMetadata"):
                # U+3164 HANGUL FILLER

                if isinstance((wsqs := gm.get("webSearchQueries")), list):
                    xlog(user, f"Made {len(wsqs)} web searches")
                    extras += (
                        "Searches:\n"
                        + "\n".join(f"\u3164- {wsq}" for wsq in wsqs)
                        + "\n"
                    )

                if isinstance((gcs := gm.get("groundingChunks")), list):
                    links = _resolve_links(
                        user,
                        [
                            uri
                            for gc in gcs
                            if isinstance(gc, dict)
                            and isinstance((web := gc.get("web")), dict)
                            and isinstance((uri := web.get("uri")), str)
                            and uri
                        ],
                    )
                    xlog(user, f"Found {len(gcs)} grounding chunks {len(links)} links")
                    extras += (
                        "Links:\n"
                        + "\n".join(f"\u3164- {link}" for link in links)
                        + "\n"
                    )

    if not text:
        # Rejection

        feedback = _get_finish_reason_feedback(gemini_result)
        if not feedback:
            xlog(user, f"No result text: {gemini_result}")
            feedback = "UNKNOWN"

        track_stats(f"g.rejected.{feedback}")
        return JaiResult(
            502,
            f"Response blocked/empty due to {feedback}.",
            metadata=JaiResultMetadata(
                rejection_feedback=feedback,
            ),
        )

    if isinstance((usage := gemini_result.get("usageMetadata")), dict):
        metadata.token_usage = JaiResultTokenUsage(
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
            reasoning_tokens=usage.get("thoughtsTokenCount"),
            total_tokens=usage.get("totalTokenCount"),
        )

    track_stats("g.succeeded")
    return JaiResult(200, text, extras=extras, metadata=metadata)
