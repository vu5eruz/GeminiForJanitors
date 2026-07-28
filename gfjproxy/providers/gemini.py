from typing import Any

import httpx2

from .._globals import PROCESS_TIMEOUT
from ..http_client import http_client
from ..logging import xlog
from ..models import JaiMessage, JaiResult, JaiResultMetadata, JaiResultTokenUsage
from ..statistics import track_stats
from ..xuiduser import XUID

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

    generation_config: dict[str, Any] = {}

    gemini_request: dict[str, Any] = {
        "safetySettings": [
            {
                "threshold": "BLOCK_NONE",
                "category": "HARM_CATEGORY_HATE_SPEECH",
            },
            {
                "threshold": "BLOCK_NONE",
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            },
            {
                "threshold": "BLOCK_NONE",
                "category": "HARM_CATEGORY_HARASSMENT",
            },
            {
                "threshold": "BLOCK_NONE",
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            },
            {
                "threshold": "BLOCK_NONE",
                "category": "HARM_CATEGORY_JAILBREAK",
            },
        ],
        "generationConfig": generation_config,
        "contents": [
            {
                "role": "user" if msg.role == "user" else "model",
                "parts": [{"text": msg.content}],
            }
            for msg in messages
        ],
    }

    for key, value in (settings or {}).items():
        if key == "temperature":
            generation_config["temperature"] = value
        elif key == "max_tokens":
            generation_config["maxOutputTokens"] = value
        elif key == "top_k":
            generation_config["topK"] = value
        elif key == "top_p":
            generation_config["topP"] = value
        elif key == "frequency_penalty":
            generation_config["frequencyPenalty"] = value
        elif key == "repetition_penalty":
            generation_config["presencePenalty"] = value
        elif key == "search" and value:
            gemini_request["tools"] = [{"googleSearch": {}}]

    try:
        response = http_client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key},
            json=gemini_request,
            timeout=PROCESS_TIMEOUT,
        )
        response.raise_for_status()
        gemini_result = response.json()
    except httpx2.TimeoutException:
        track_stats("g.time_out")
        return JaiResult(504, "Gateway Timeout")
    except httpx2.HTTPStatusError as e:
        message = "Error from Google AI"
        metadata = JaiResultMetadata()

        if e.response.is_client_error:
            stats_key = "g.failed.client"
        elif e.response.is_server_error:
            stats_key = "g.failed.server"
        else:
            stats_key = "g.failed.unknown"

        if error := e.response.json():
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
        return JaiResult(e.response.status_code, message, metadata=metadata)
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
                text = ""
                for part in parts:
                    if isinstance(part, dict):
                        part_text = part.get("text")
                        part_thought = part.get("thought", False)
                        if isinstance(part_text, str) and not part_thought:
                            text += part_text

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
                    links: list[str] = []
                    for gc in gcs:
                        if (
                            isinstance(gc, dict)
                            and (web := gc.get("web"))
                            and isinstance(web, dict)
                            and (uri := web.get("uri"))
                        ):
                            links.append(_resolve_link(user, uri))
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
