from typing import Any

import httpx

from .._globals import PROCESS_TIMEOUT
from ..http_client import http_client
from ..logging import xlog
from ..models import JaiMessage, JaiResult, JaiResultMetadata, JaiResultTokenUsage
from ..statistics import track_stats
from ..xuiduser import XUID


def z_ai_generate_content(
    user: XUID,
    api_key: str,
    model: str,
    messages: list[JaiMessage],
    settings: dict[str, Any] = {},
) -> JaiResult:
    """Wrapper around Z.AI's Chat Completions API.
    API keys must be prefixed with "z_ai/" to help the handlers distinguish them,
    as official Z.AI's API keys don't have any prefix.

    User paramater is only used for logging."""

    z_ai_request = {
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
            z_ai_request["temperature"] = value
        elif key == "top_p":
            z_ai_request["top_p"] = value

    try:
        z_ai_response = http_client.post(
            "https://api.z.ai/api/paas/v4/chat/completions",
            json=z_ai_request,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=PROCESS_TIMEOUT,
        )
        z_ai_response.raise_for_status()
        z_ai_result = z_ai_response.json()
    except httpx.TimeoutException:
        track_stats("z_ai.time_out")
        return JaiResult(504, "Gateway Timeout")
    except httpx.HTTPStatusError as e:
        message = "Error from Z.AI"

        if error := e.response.json().get("error"):
            if error_code := error.get("code"):
                message += f" ({error_code})"
            if error_message := error.get("message"):
                message += f": {error_message}"
        else:
            xlog(user, f"{message}: {e.response.text!r}")

        if e.response.is_client_error:
            track_stats("z_ai.failed.client")
        elif e.response.is_server_error:
            track_stats("z_ai.failed.server")
        else:
            track_stats("z_ai.failed.unknown")

        return JaiResult(e.response.status_code, message)
    except Exception as e:
        xlog(user, repr(e))
        track_stats("z_ai.failed.exception")
        return JaiResult(502, "Unhanded exception from Z.AI.")

    text = ""
    extras = ""
    metadata = JaiResultMetadata()

    message = {}

    if (
        isinstance(z_ai_result, dict)
        and isinstance(choices := z_ai_result.get("choices"), list)
        and len(choices) > 0
        and isinstance(choices[0], dict)
        and isinstance(message := choices[0].get("message"), dict)
    ):
        text = message.get("content", "")

    if usage := z_ai_result.get("usage"):
        metadata.token_usage = JaiResultTokenUsage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            reasoning_tokens=usage.get("completion_tokens_details", {}).get(
                "reasoning_tokens"
            ),
            total_tokens=usage.get("total_tokens"),
        )

    if not text and isinstance(message, dict):
        # The `//think on` jailbreak seems to make Z.AI models spill
        # the response into "reasoning_content" instead of "content".
        # Hopefully handlers.py can handle this down the line.
        text = message.get("reasoning_content", "")
        if "<response>" not in text and "</response>" not in text:
            extras = "Z.AI returned anomalous response. The `//think` command might cause this."

    if not text:
        # Rejection?
        xlog(user, f"No result text: {z_ai_result!r}")
        track_stats("z_ai.rejected")
        return JaiResult(502, "Response blocked/empty.", metadata=metadata)

    track_stats("z_ai.succeeded")
    return JaiResult(200, text, extras=extras, metadata=metadata)
