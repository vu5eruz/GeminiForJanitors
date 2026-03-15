from typing import Any

from httpx import ReadTimeout

from .._globals import PROCESS_TIMEOUT
from ..http_client import http_client
from ..logging import xlog
from ..models import JaiMessage, JaiResult, JaiResultMetadata, JaiResultTokenUsage
from ..statistics import track_stats
from ..xuiduser import XUID


def cerebras_generate_content(
    user: XUID,
    api_key: str,
    model: str,
    messages: list[JaiMessage],
    settings: dict[str, Any] = {},
) -> JaiResult:
    """Wrapper around Cerebras' Chat Completions API.

    User paramater is only used for logging."""

    cerebras_request = {
        "model": model,
        "stream": False,
        "temperature": settings.get("temperature"),
        "top_p": settings.get("top_p"),
        "messages": [
            {
                "content": message.content,
                "role": message.role,
            }
            for message in messages
        ],
    }

    try:
        cerebras_response = http_client.post(
            "https://api.cerebras.ai/v1/chat/completions",
            json=cerebras_request,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=PROCESS_TIMEOUT,
        )
    except ReadTimeout:
        track_stats("cerebras.time_out")
        return JaiResult(504, "Gateway Timeout")
    except Exception as e:
        xlog(user, repr(e))
        track_stats("cerebras.failed.unknown.exception")
        return JaiResult(502, "Unhanded exception from Cerebras Inference.")

    cerebras_result: dict[str, Any] = {}
    if cerebras_response.headers.get("content-type", "").startswith("application/json"):
        cerebras_result = cerebras_response.json()

    if not cerebras_response.is_success:
        xlog(
            user,
            " ".join(
                [
                    str(cerebras_response.status_code),
                    cerebras_response.reason_phrase,
                    repr(cerebras_result),
                ]
            ),
        )

        if cerebras_response.is_client_error:
            track_stats("cerebras.failed.client.unknown")
        elif cerebras_response.is_server_error:
            track_stats("cerebras.failed.server.unknown")
        else:
            track_stats("cerebras.failed.unknown")

        return JaiResult(cerebras_response.status_code, cerebras_response.reason_phrase)

    text = ""
    extras = ""
    metadata = JaiResultMetadata()

    if choices := cerebras_result.get("choices"):
        if isinstance(choices[0], dict) and (message := choices[0].get("message")):
            text = message.get("content")

    if usage := cerebras_result.get("usage"):
        metadata.token_usage = JaiResultTokenUsage(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

    if not text:
        # Rejection?
        xlog(user, f"No result text: {cerebras_result!r}")
        track_stats("cerebras.rejected")
        return JaiResult(502, "Response blocked/empty.", metadata=metadata)

    track_stats("cerebras.succeeded")
    return JaiResult(200, text, extras=extras, metadata=metadata)
