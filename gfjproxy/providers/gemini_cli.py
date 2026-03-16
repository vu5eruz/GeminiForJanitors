import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Self
from uuid import uuid4

import httpx

from .._globals import PROCESS_TIMEOUT, PROXY_URL
from ..http_client import http_client
from ..logging import xlog, xlogtime
from ..models import JaiMessage, JaiResult, JaiResultMetadata, JaiResultTokenUsage
from ..statistics import track_stats
from ..storage import storage
from ..utils import base64url_decode, utcfromtimestamp, utcnow
from ..xuiduser import XUID

# https://github.com/google-gemini/gemini-cli/blob/17b37144a96da13bf7a0917411bc1d34142609d7/packages/core/src/code_assist/oauth2.ts#L72
CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
CLIENT_SECRET = "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"

# https://github.com/googleapis/google-cloud-python/blob/b9466f9c85c94331ffc39e1da3cf98fb5ff7d612/packages/google-auth/google/auth/_helpers.py#L42
REFRESH_THRESHOLD = timedelta(minutes=3, seconds=45)


# https://github.com/badlogic/pi-mono/blob/83378aad7e74a0e2bb8f37c007a9685fb4609d8a/packages/ai/src/utils/oauth/google-gemini-cli.ts#L232
def _make_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "google-api-nodejs-client/9.15.1",
        "X-Goog-Api-Client": "gl-node/22.17.0",
    }


# Based on the data model of ~/.gemini/oauth_creds.json
@dataclass(kw_only=True, slots=True, frozen=True)
class Credentials:
    access_token: str
    expiry_date: datetime
    id_token: str
    refresh_token: str
    scope: str

    def expired(self) -> float:
        """Calculates the credentials expiration time in fractional seconds.

        Returns:
            float: Positive seconds of how long the credentials have expired, or
                   negative seconds of how long until the credentials expire.
        """
        # https://github.com/googleapis/google-cloud-python/blob/b9466f9c85c94331ffc39e1da3cf98fb5ff7d612/packages/google-auth/google/auth/credentials.py#L90
        skewed_expiry = self.expiry_date - REFRESH_THRESHOLD
        return (utcnow() - skewed_expiry).total_seconds()

    @staticmethod
    def parse(data: dict) -> "Credentials":
        access_token = data.get("access_token")
        if not isinstance(access_token, str):
            raise ValueError("Missing/invalid access_token")

        id_token = data.get("id_token")
        if not isinstance(id_token, str):
            raise ValueError("Missing/invalid id_token")

        refresh_token = data.get("refresh_token")
        if not isinstance(refresh_token, str):
            raise ValueError("Missing/invalid refresh_token")

        expiry_date = data.get("expiry_date")
        if not isinstance(expiry_date, (int, float)):
            raise ValueError("Missing/invalid expiry_date")

        scope = data.get("scope")
        if not isinstance(scope, str):
            raise ValueError("Missing/invalid scope")

        token_type = data.get("token_type")
        if token_type != "Bearer":
            raise ValueError("Missing/invalid token_type")

        return Credentials(
            access_token=access_token,
            expiry_date=utcfromtimestamp(expiry_date / 1000),
            id_token=id_token,
            refresh_token=refresh_token,
            scope=scope,
        )

    def json(self):
        return {
            "access_token": self.access_token,
            "id_token": self.id_token,
            "refresh_token": self.refresh_token,
            "expiry_date": self.expiry_date.timestamp() * 1000,
            "scope": self.scope,
            "token_type": "Bearer",
        }


@dataclass(kw_only=True, slots=True, frozen=True)
class Result[TValue, TError]:
    _is_success: bool
    _value: TValue | None = None
    _error: TError | None = None

    @classmethod
    def from_value(cls, value: TValue) -> Self:
        return cls(_is_success=True, _value=value)

    @classmethod
    def from_error(cls, error: TError) -> Self:
        return cls(_is_success=False, _error=error)

    @property
    def success(self) -> bool:
        return self._is_success

    @property
    def value(self) -> TValue:
        if not self._is_success:
            raise RuntimeError(f"Accessed value of a failed {type(self).__name__}")
        return self._value  # type: ignore

    @property
    def error(self) -> TError:
        if self._is_success:
            raise RuntimeError(f"Accessed error of a successful {type(self).__name__}")
        return self._error  # type: ignore


@dataclass(kw_only=True, slots=True, frozen=True)
class RefreshCredentialsResult(Result[Credentials, tuple[int, str]]):
    pass


@dataclass(kw_only=True, slots=True, frozen=True)
class LoadProjectIdResult(Result[str, tuple[int, str]]):
    pass


@dataclass(kw_only=True, slots=True, frozen=True)
class GenerateContentExResult(Result[dict[str, Any], tuple[int, str]]):
    pass


def gemini_cli_refresh_credentials(
    user: XUID | None, credentials: Credentials
) -> RefreshCredentialsResult:
    """Refreshes credentials for Gemini CLI.
    This might return a reference to the provided credentials.
    """
    expired = credentials.expired()
    if expired < 0:
        xlog(user, "Credentials are fresh!")
        return RefreshCredentialsResult.from_value(credentials)

    ref_time = xlogtime(user, f"Refreshing credentials (expired {expired:.0f}s ago)")

    timestamp = utcnow()

    try:
        # https://github.com/badlogic/pi-mono/blob/83378aad7e74a0e2bb8f37c007a9685fb4609d8a/packages/ai/src/utils/oauth/google-gemini-cli.ts#L380
        resp = http_client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "refresh_token": credentials.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        resp_json = resp.json()
    except httpx.TimeoutException:
        return RefreshCredentialsResult.from_error((504, "Google OAuth timed out"))
    except httpx.HTTPStatusError as e:
        message = f"Refresh credentials error: {e.response.status_code} {e.response.reason_phrase}"
        xlog(user, f"{message}\n{e.response.text!r}")
        return RefreshCredentialsResult.from_error((e.response.status_code, message))
    except httpx.RequestError as e:
        message = f"Refresh credentials network error: {e}"
        xlog(user, message)
        return RefreshCredentialsResult.from_error((502, message))
    except Exception as e:
        xlog(user, f"Refresh credentials unexpected error: {e!r}")
        return RefreshCredentialsResult.from_error((500, "Unknown exception"))

    xlogtime(user, "Refreshed credentials!", ref_time)

    expiry_date = timestamp + timedelta(seconds=resp_json.get("expires_in", 0))

    return RefreshCredentialsResult.from_value(
        Credentials(
            access_token=resp_json.get("access_token", credentials.access_token),
            expiry_date=expiry_date,
            id_token=resp_json.get("id_token", credentials.id_token),
            refresh_token=resp_json.get("refresh_token", credentials.refresh_token),
            scope=resp_json.get("scope", credentials.scope),
        )
    )


def gemini_cli_load_project_id(
    user: XUID | None, credentials: Credentials
) -> LoadProjectIdResult:
    """Loads Google Cloud project id for Gemini CLI.
    This method will fail if the user is not onboarded.
    """
    headers = _make_headers(credentials.access_token)

    ref_time = xlogtime(user, "Loading project id")

    try:
        # https://github.com/badlogic/pi-mono/blob/83378aad7e74a0e2bb8f37c007a9685fb4609d8a/packages/ai/src/utils/oauth/google-gemini-cli.ts#L241
        resp = http_client.post(
            "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
            headers=headers,
            json={
                "metadata": {
                    "ideType": "IDE_UNSPECIFIED",
                    "platform": "PLATFORM_UNSPECIFIED",
                    "pluginType": "GEMINI",
                }
            },
        )
        resp.raise_for_status()
        resp_json = resp.json()
    except httpx.TimeoutException:
        return LoadProjectIdResult.from_error((504, "Google Cloud Code timed out"))
    except httpx.HTTPStatusError as e:
        message = f"Load project id error: {e.response.status_code} {e.response.reason_phrase}"
        xlog(user, f"{message}\n{e.response.text!r}")
        return LoadProjectIdResult.from_error((e.response.status_code, message))
    except httpx.RequestError as e:
        message = f"Load project id network error: {e}"
        xlog(user, message)
        return LoadProjectIdResult.from_error((502, message))
    except Exception as e:
        xlog(user, f"Load project id unexpected error: {e!r}")
        return LoadProjectIdResult.from_error((500, "Unknown exception"))

    if not resp_json.get("currentTier"):
        return LoadProjectIdResult.from_error(
            (403, "User isn't onboarded to Gemini CLI")
        )

    project_id = resp_json.get("cloudaicompanionProject")
    if not project_id:
        return LoadProjectIdResult.from_error(
            (403, "User needs to provide a project id")
        )

    xlogtime(user, "Loaded project id!", ref_time)

    return LoadProjectIdResult.from_value(project_id)


def gemini_cli_generate_content_ex(
    user: XUID | None,
    access_token: str,
    project_id: str,
    model: str,
    messages: list[JaiMessage],
    settings: dict[str, Any] = {},
) -> GenerateContentExResult:
    ref_time = xlogtime(user, "Gemini CLI generating")

    session_id = str(uuid4())

    contents = [
        {
            "role": "model" if message.role == "assistant" else "user",
            "parts": [{"text": message.content}],
        }
        for message in messages
    ]

    try:
        # https://github.com/badlogic/pi-mono/blob/83378aad7e74a0e2bb8f37c007a9685fb4609d8a/packages/ai/src/providers/google-gemini-cli.ts#L265
        resp = http_client.post(
            "https://cloudcode-pa.googleapis.com/v1internal:generateContent",
            headers=_make_headers(access_token),
            json={
                "project": project_id,
                "model": model,
                "request": {
                    "contents": contents,
                    "sessionId": session_id,
                    "generationConfig": {
                        "temperature": settings.get("temperature", 1),
                    },
                },
            },
            timeout=PROCESS_TIMEOUT,
        )
        resp.raise_for_status()
        resp_json = resp.json()
    except httpx.TimeoutException:
        return GenerateContentExResult.from_error((504, "Google Cloud Code timed out"))
    except httpx.HTTPStatusError as e:
        error_json = {}
        if e.response.headers.get("content-type", "").startswith("application/json"):
            error_json = e.response.json()

        message = f"Gemini CLI generate error: {e.response.status_code} {e.response.reason_phrase}"

        if isinstance((error := error_json.get("error")), dict):
            if error_status := error.get("status", ""):
                message += f" ({error_status})"
            if error_message := error.get("message", ""):
                message += f": {error_message}"

        xlog(user, f"{message}\n{(error_json or e.response.text)!r}")
        return GenerateContentExResult.from_error((e.response.status_code, message))
    except httpx.RequestError as e:
        message = f"Gemini CLI generate network error: {e}"
        xlog(user, message)
        return GenerateContentExResult.from_error((502, message))
    except Exception as e:
        xlog(user, f"Gemini CLI generate unexpected error: {e!r}")
        return GenerateContentExResult.from_error((500, "Unknown exception"))

    xlogtime(user, "Gemini CLI generated!", ref_time)

    return GenerateContentExResult.from_value(resp_json)


def gemini_cli_generate_content(
    user: XUID,
    api_key: str,
    model: str,
    messages: list[JaiMessage],
    settings: dict[str, Any] = {},
) -> JaiResult:
    """Wrapper around gemini_cli_generate_content_ex for use by proxy handlers.

    User paramater is only used for logging. Generation settings must all be passed inside the
    settings parameter."""

    raw_credentials = storage.keyring_get(api_key)
    if not raw_credentials:
        this_proxy_url = PROXY_URL.rstrip("/")

        message = "API key not valid."
        proxy_url = base64url_decode(api_key.split(".")[2]).decode().rstrip("/")
        if proxy_url != this_proxy_url:
            message = f"This API key is from another proxy ({proxy_url})."

        message += f" You need to create an API key on this proxy's keyring ({this_proxy_url}/keyring)."

        track_stats("g_cli.failed.client.invalid.api_key")
        return JaiResult(
            400,
            message,
            metadata=JaiResultMetadata(
                api_key_valid=False,
            ),
        )

    try:
        credentials = Credentials.parse(json.loads(raw_credentials))
    except Exception as e:  # This shoud never happen
        xlog(user, f"Exception while loading credentials from keyring: {e!r}")
        track_stats("g_cli.failed.system.creds")
        return JaiResult(500, "Invalid/missing credentials in API key")

    rcr = gemini_cli_refresh_credentials(user, credentials)
    if not rcr.success:
        error_code, error_message = rcr.error
        track_stats("g_cli.failed.system.refresh")
        return JaiResult(error_code, error_message)
    credentials = rcr.value

    storage.keyring_put(api_key, json.dumps(credentials.json()))

    lpidr = gemini_cli_load_project_id(user, credentials)
    if not lpidr.success:
        error_code, error_message = lpidr.error
        track_stats("g_cli.failed.system.load")
        return JaiResult(error_code, error_message)
    project_id = lpidr.value

    gcexr = gemini_cli_generate_content_ex(
        user,
        credentials.access_token,
        project_id,
        model,
        messages,
        settings,
    )
    if not gcexr.success:
        error_code, error_message = gcexr.error
        track_stats("g_cli.failed")
        return JaiResult(error_code, error_message)
    result: dict[str, Any] = gcexr.value.get("response", {})

    text = ""
    extras = ""
    metadata = JaiResultMetadata()

    # lol
    if (
        result
        and isinstance((candidates := result.get("candidates")), list)
        and len(candidates) > 0
        and isinstance((candidate := candidates[0]), dict)
        and isinstance((content := candidate.get("content")), dict)
        and isinstance((parts := content.get("parts")), list)
        and len(parts) > 0
        and isinstance((part := parts[0]), dict)
        and isinstance((part_text := part.get("text")), str)
    ):
        # lmao even
        text = part_text

    if isinstance((usage := result.get("usageMetadata")), dict):
        metadata.token_usage = JaiResultTokenUsage(
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
            reasoning_tokens=usage.get("thoughtsTokenCount"),
            total_tokens=usage.get("totalTokenCount"),
        )

    if not text:
        # Rejection?
        xlog(user, f"No result text: {result!r}")
        track_stats("g_cli.rejected")
        return JaiResult(502, "Response blocked/empty.", metadata=metadata)

    track_stats("g_cli.succeeded")
    return JaiResult(200, text, extras=extras, metadata=metadata)
