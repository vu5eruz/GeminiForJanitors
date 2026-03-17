from typing import Any

import httpx

from .._globals import PROCESS_TIMEOUT, PROXY_NAME, PROXY_URL
from ..http_client import http_client
from ..logging import xlog
from ..models import JaiMessage, JaiResult, JaiResultMetadata, JaiResultTokenUsage
from ..statistics import track_stats
from ..xuiduser import XUID


def openrouter_generate_content(
    user: XUID,
    api_key: str,
    model: str,
    messages: list[JaiMessage],
    settings: dict[str, Any] = {},
) -> JaiResult:
    """Wrapper around OpenRouter's Chat Completions API.

    User paramater is only used for logging."""

    openrouter_request = {
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
            openrouter_request["temperature"] = value
        elif key == "max_tokens":
            openrouter_request["max_tokens"] = value
        elif key == "top_k":
            openrouter_request["top_k"] = value
        elif key == "top_p":
            openrouter_request["top_p"] = value
        elif key == "frequency_penalty":
            openrouter_request["frequency_penalty"] = value
        elif key == "repetition_penalty":
            openrouter_request["presence_penalty"] = value

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": PROXY_URL,
        "X-Title": PROXY_NAME,
    }

    try:
        openrouter_response = http_client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=openrouter_request,
            headers=headers,
            timeout=PROCESS_TIMEOUT,
        )
        openrouter_response.raise_for_status()
        openrouter_result = openrouter_response.json()
    except httpx.TimeoutException:
        track_stats("openrouter.time_out")
        return JaiResult(504, "Gateway Timeout")
    except httpx.HTTPStatusError as e:
        message = "Error from OpenRouter"

        if isinstance(error := e.response.json().get("error"), dict):
            if error_code := error.get("code"):
                message += f" ({error_code})"
            if error_message := error.get("message"):
                message += f": {error_message}"
        else:
            xlog(user, f"{message}: {e.response.text!r}")

        if e.response.is_client_error:
            track_stats("openrouter.failed.client")
        elif e.response.is_server_error:
            track_stats("openrouter.failed.server")
        else:
            track_stats("openrouter.failed.unknown")

        return JaiResult(e.response.status_code, message)
    except Exception as e:
        xlog(user, repr(e))
        track_stats("openrouter.failed.exception")
        return JaiResult(502, "Unhanded exception from OpenRouter.")

    text = ""
    metadata = JaiResultMetadata()

    if choices := openrouter_result.get("choices"):
        if isinstance(choices[0], dict) and (message := choices[0].get("message")):
            text = message.get("content")

    if usage := openrouter_result.get("usage"):
        metadata.token_usage = JaiResultTokenUsage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

    if not text:
        # Rejection?
        xlog(user, f"No result text: {openrouter_result!r}")
        track_stats("openrouter.rejected")
        return JaiResult(502, "Response blocked/empty.", metadata=metadata)

    track_stats("openrouter.succeeded")
    return JaiResult(200, text, metadata=metadata)
