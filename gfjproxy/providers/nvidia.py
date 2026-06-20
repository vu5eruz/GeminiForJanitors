from typing import Any

import httpx2

from .._globals import PROCESS_TIMEOUT
from ..http_client import http_client
from ..logging import xlog
from ..models import JaiMessage, JaiResult, JaiResultMetadata, JaiResultTokenUsage
from ..statistics import track_stats
from ..xuiduser import XUID


def _simplify_error_message(message: str) -> str:
    if not message:
        return "[empty error message]"

    # Nvidia sometimes seems to send duplicated error messages in the same string
    # I.e. the first half of the string is equal to the second half, separated by a space
    half_len = len(message) // 2
    if message[half_len] == " " and message[:half_len] == message[half_len + 1 :]:
        return message[:half_len]

    # No simplifications done
    return message


def nvidia_generate_content(
    user: XUID,
    api_key: str,
    model: str,
    messages: list[JaiMessage],
    settings: dict[str, Any] = {},
) -> JaiResult:
    """Wrapper around Nvidia NIM API.

    User paramater is only used for logging."""

    nvidia_request = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "content": message.content,
                "role": message.role,
            }
            for message in messages
        ],
    }

    for key, value in settings.items():
        if key == "temperature":
            nvidia_request["temperature"] = value
        elif key == "max_tokens":
            nvidia_request["max_tokens"] = value
        elif key == "top_k":
            nvidia_request["top_k"] = value
        elif key == "top_p":
            nvidia_request["top_p"] = value
        elif key == "frequency_penalty":
            nvidia_request["frequency_penalty"] = value
        elif key == "repetition_penalty":
            nvidia_request["presence_penalty"] = value

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    try:
        nvidia_response = http_client.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            json=nvidia_request,
            headers=headers,
            timeout=PROCESS_TIMEOUT,
        )
        nvidia_response.raise_for_status()
        nvidia_result = nvidia_response.json()
    except httpx2.TimeoutException:
        track_stats("nvidia.time_out")
        return JaiResult(504, "Gateway Timeout")
    except httpx2.HTTPStatusError as e:
        message = "Error from Nvidia NIM"
        extras = ""

        content_type: str | None
        if content_type := e.response.headers.get("content-type"):
            if content_type.startswith("text/plain"):
                message += f": {e.response.text}"
            elif content_type.startswith("application/json"):
                if isinstance((error := e.response.json().get("error")), dict):
                    if error_code := error.get("code"):
                        message += f" ({error_code})"
                    if error_message := error.get("message"):
                        message += f": {_simplify_error_message(error_message)}"
            elif content_type.startswith("application/problem+json"):
                response_json = e.response.json()

                if title := response_json.get("title"):
                    message += f" ({title})"
                if detail := response_json.get("detail"):
                    message += f": {detail}"
            else:
                xlog(user, f"{message}: {e.response.text!r}")

        if e.response.is_client_error:
            track_stats("nvidia.failed.client")
        elif e.response.is_server_error:
            track_stats("nvidia.failed.server")
        else:
            track_stats("nvidia.failed.unknown")

        return JaiResult(e.response.status_code, message, extras=extras)
    except Exception as e:
        xlog(user, repr(e))
        track_stats("nvidia.failed.exception")
        return JaiResult(502, "Unhanded exception from Nvidia NIM.")

    text = ""
    metadata = JaiResultMetadata()

    if choices := nvidia_result.get("choices"):
        if isinstance(choices[0], dict) and (message := choices[0].get("message")):
            text = message.get("content")

    if usage := nvidia_result.get("usage"):
        metadata.token_usage = JaiResultTokenUsage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

    if not text:
        # Rejection?
        xlog(user, f"No result text: {nvidia_result!r}")
        track_stats("nvidia.rejected")
        return JaiResult(502, "Response blocked/empty.", metadata=metadata)

    track_stats("nvidia.succeeded")
    return JaiResult(200, text, metadata=metadata)
