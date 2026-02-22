from typing import Any

from google import genai
from google.genai import errors, types
from httpx import HTTPError, ReadTimeout

from .._globals import PROCESS_TIMEOUT
from ..http_client import http_client
from ..logging import xlog
from ..models import JaiMessage, JaiResult, JaiResultMetadata
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
    except HTTPError as e:
        xlog(user, f"Could not resolve link:\n{e!r}")

    if result != link:
        xlog(user, "Link resolved")
    else:
        xlog(user, "Link not resolved")

    return result


def _get_finish_reason_feedback(response: types.GenerateContentResponse) -> str | None:
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


def _get_quota_violation_feedback(qid: str) -> str | None:
    """Converts a quota ID into a human-readable message.

    Returns None if an unknown quota ID is given."""

    if qid.startswith("GenerateContentInputTokensPerModelPerMinute") or qid.startswith(
        "GenerateContentPaidTierInputTokensPerModelPerMinute"
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
    settings: dict[str, Any] = {},
) -> JaiResult:
    """Wrapper around Google AI's Gemini.

    User paramater is only used for logging. Generation settings must all be passed inside the
    settings parameter."""

    gemini_config: types.GenerateContentConfigDict = {
        "http_options": {
            "timeout": PROCESS_TIMEOUT * 1_000  # milliseconds
        },
        "safety_settings": [
            {
                "threshold": types.HarmBlockThreshold.BLOCK_NONE,
                "category": types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            },
            {
                "threshold": types.HarmBlockThreshold.BLOCK_NONE,
                "category": types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            },
            {
                "threshold": types.HarmBlockThreshold.BLOCK_NONE,
                "category": types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            },
            {
                "threshold": types.HarmBlockThreshold.BLOCK_NONE,
                "category": types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            },
        ],
    }

    for key, value in settings.items():
        if key == "temperature":
            gemini_config["temperature"] = value
        elif key == "max_tokens":
            gemini_config["max_output_tokens"] = value
        elif key == "top_k":
            gemini_config["top_k"] = value
        elif key == "top_p":
            gemini_config["top_p"] = value
        elif key == "frequency_penalty":
            gemini_config["frequency_penalty"] = value
        elif key == "repetition_penalty":
            gemini_config["presence_penalty"] = value
        elif key == "search" and value:
            gemini_config["tools"] = [types.Tool(google_search=types.GoogleSearch())]

    gemini_contents = []
    for msg in messages:
        if msg.role == "assistant" or msg.role == "system":
            gemini_contents.append(types.ModelContent({"text": msg.content}))
        else:
            gemini_contents.append(types.UserContent({"text": msg.content}))

    gemini_client = genai.Client(api_key=api_key)

    try:
        gemini_result = gemini_client.models.generate_content(
            model=model, contents=gemini_contents, config=gemini_config
        )
    except ReadTimeout:
        track_stats("g.time_out")
        return JaiResult(504, "Gateway Timeout")
    except errors.ClientError as e:
        if e.message is None:  # Make type checkers happy
            e.message = "Unknown error"

        if e.status == "NOT_FOUND":
            # 404 NOT_FOUND "models/* is not found for API version v1beta"
            if e.message.startswith("models/"):
                track_stats("g.failed.client.not_found.model")
                return JaiResult(e.code, f"Invalid/unsupported model '{model}'")

            xlog(user, repr(e))  # Anomalous
            track_stats("g.failed.client.not_found.unknown")
            return JaiResult(e.code, e.message)

        if e.status == "INVALID_ARGUMENT":
            if "API key not valid" in e.message:
                # 400 INVALID_ARGUMENT "API key not valid. Please pass a valid API key."
                track_stats("g.failed.client.invalid.api_key")
                return JaiResult(
                    e.code,
                    e.message,
                    metadata=JaiResultMetadata(
                        api_key_valid=False,
                    ),
                )

            # 400 INVALID_ARGUMENT "Penalty is not enabled for models/*"
            track_stats("g.failed.client.invalid")
            return JaiResult(e.code, e.message)

        details: list[Any] = []
        if isinstance(e.details, dict):
            details.extend(
                e.details.get("details", e.details.get("error", {}).get("details", []))
            )

        if e.status == "PERMISSION_DENIED":
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                if detail.get("@type") != "type.googleapis.com/google.rpc.ErrorInfo":
                    continue

                if reason := detail.get("reason"):
                    if reason == "SERVICE_DISABLED":
                        # This error could either refer to an misconfigured API
                        # key or an banned user.
                        track_stats("g.failed.client.denied.disabled")
                        return JaiResult(
                            e.code, "Generative Language API needs to be enabled"
                        )

                    if reason == "CONSUMER_SUSPENDED":
                        # This error is most likely a banned user.
                        track_stats("g.failed.client.denied.suspended")
                        return JaiResult(
                            e.code, "Customer suspended. You might be banned."
                        )

            # 403 PERMISSION_DENIED "Consumer 'api_key:*' has been suspended."
            track_stats("g.failed.client.denied.unknown")
            return JaiResult(e.code, e.message)

        if e.status == "RESOURCE_EXHAUSTED":
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                if detail.get("@type") != "type.googleapis.com/google.rpc.QuotaFailure":
                    continue

                for violation in detail.get("violations", []):
                    qid = violation.get("quotaId")

                    if feedback := _get_quota_violation_feedback(qid):
                        track_stats(f"g.failed.client.quota.violation.{qid}")
                        return JaiResult(e.code, feedback)

            # 429 RESOURCE_EXHAUSTED "Resource has been exhausted (e.g. check quota)."
            track_stats("g.failed.client.quota.unknown")
            return JaiResult(e.code, e.message)

        xlog(user, repr(e))  # Log these fellas for they are anomalous
        track_stats("g.failed.client.unknown")
        return JaiResult(e.code, e.message)
    except errors.ServerError as e:
        if e.message is None:  # Make type checkers happy
            e.message = "Unknown error"

        if e.status == "UNAVAILABLE":
            # 503 UNAVAILABLE "The model is overloaded. Please try again later."
            track_stats("g.failed.server.overloaded")
            return JaiResult(e.code, e.message)

        if e.status == "DEADLINE_EXCEEDED":
            # 504 DEADLINE_EXCEEDED "The request timed out. Please try again."
            track_stats("g.failed.server.time_out")
            return JaiResult(e.code, "Google AI timed out. Try again later.")

        if e.status == "INTERNAL":
            # 500 INTERNAL "An internal error has occurred."
            # The actual message is longer and not really relevant to the users.
            # Skip logging these errors and return our own message instead.
            track_stats("g.failed.server.internal")
            return JaiResult(
                e.code, "Google AI had an internal error. Try again later."
            )

        xlog(user, repr(e))  # Log these fellas for they are anomalous
        track_stats("g.failed.server.unknown")
        return JaiResult(e.code, e.message)
    except Exception as e:
        xlog(user, repr(e))  # These are R E A L L Y anomalous
        track_stats("g.failed.unknown")
        return JaiResult(502, "Unhanded exception from Google AI.")

    text = ""
    extras = ""
    metadata = JaiResultMetadata()

    if candidates := gemini_result.candidates:
        if len(candidates) > 1:
            xlog(user, "Warning: more than one candidate found in response")
        candidate: types.Candidate = candidates[0]

        if candidate.content and (parts := candidate.content.parts):
            text = ""
            for part in parts:
                if isinstance(part.text, str) and not part.thought:
                    text += part.text

        if gm := candidate.grounding_metadata:
            # U+3164 HANGUL FILLER

            if isinstance((wsqs := gm.web_search_queries), list):
                xlog(user, f"Made {len(wsqs)} web searches")
                extras += (
                    "Searches:\n" + "\n".join(f"\u3164- {wsq}" for wsq in wsqs) + "\n"
                )

            if isinstance((gcs := gm.grounding_chunks), list):
                links: list[str] = []
                for gc in gcs:
                    if (web := gc.web) and (uri := web.uri):
                        links.append(_resolve_link(user, uri))
                xlog(user, f"Found {len(gcs)} grounding chunks {len(links)} links")
                extras += (
                    "Links:\n" + "\n".join(f"\u3164- {link}" for link in links) + "\n"
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

    if isinstance(
        gemini_result.usage_metadata, types.GenerateContentResponseUsageMetadata
    ):
        metadata.token_usage = gemini_result.usage_metadata

    track_stats("g.succeeded")
    return JaiResult(200, text, extras=extras, metadata=metadata)
