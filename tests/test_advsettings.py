import json

import pytest
from google.genai import types
from pytest_mock import MockerFixture

from gfjproxy.handlers import handle_chat_message
from gfjproxy.models import JaiMessage, JaiRequest
from gfjproxy.providers.gemini_cli import Credentials
from gfjproxy.storage import storage
from gfjproxy.utils import ResponseHelper
from gfjproxy.xuiduser import XUID, UserSettings

ADVSETTINGS = [
    "temperature",
    "frequency_penalty",
    "repetition_penalty",
    "top_k",
    "top_p",
]

ADVSETTINGS_TEST_DATA: list[dict[str, int | float]] = [
    {
        # No settings used
    },
    {
        "temperature": 0.69,
    },
    {
        "temperature": 0.42,
        "top_k": 95,
    },
    {
        "temperature": 1.23,
        "top_k": 25,
        "top_p": 0.75,
    },
    {
        "temperature": 2.00,
        "frequency_penalty": 1.5,
        "repetition_penalty": -1.5,
    },
    {
        "temperature": 1.00,
        "frequency_penalty": 0.5,
        "repetition_penalty": -0.5,
        "top_k": 75,
        "top_p": 0.25,
    },
]


@pytest.mark.parametrize(
    "provider", ["cerebras", "gemini_cli", "google", "openrouter", "z_ai"]
)
@pytest.mark.parametrize("advsettings", ADVSETTINGS_TEST_DATA)
def test_advset_this(
    mocker: MockerFixture, provider: str, advsettings: dict[str, int | float]
):
    """Check that the given advanced settings are being applied."""

    if provider == "google":
        mock_client = mocker.patch("gfjproxy.providers.gemini.genai.Client")
        mock_call = mock_client.return_value.models.generate_content
        mock_response = mocker.MagicMock(spec=types.GenerateContentResponse)
        mock_part = mocker.MagicMock(spec=types.Part)
        mock_part.text = "Bot response"
        mock_part.thought = False
        mock_candidate = mocker.MagicMock(spec=types.Candidate)
        mock_candidate.content = mocker.MagicMock(spec=types.Content)
        mock_candidate.content.parts = [mock_part]
        mock_candidate.grounding_metadata = None
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = None
        mock_call.return_value = mock_response
    else:
        mock_call = mocker.patch(f"gfjproxy.providers.{provider}.http_client.post")
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Bot response"}}],
            "response": {
                "candidates": [{"content": {"parts": [{"text": "Bot response"}]}}],
            },
        }
        mock_response.raise_for_status.return_value = None
        mock_call.return_value = mock_response

    if provider == "gemini_cli":
        credentials = {
            "access_token": "a",
            "id_token": "b",
            "refresh_token": "c",
            "expiry_date": 0,
            "scope": "d",
            "token_type": "Bearer",
        }

        storage.keyring_put("test-key", json.dumps(credentials))

        mock_credentials = mocker.MagicMock(spec=Credentials)
        mock_credentials.access_token = "a"
        mock_credentials.json = lambda: {}

        mock_refresh_credentials = mocker.patch(
            "gfjproxy.providers.gemini_cli.gemini_cli_refresh_credentials"
        )
        mock_refresh_credentials_result = mocker.Mock()
        mock_refresh_credentials_result.success = True
        mock_refresh_credentials_result.value = mock_credentials
        mock_refresh_credentials.return_value = mock_refresh_credentials_result

        mock_load_project_id = mocker.patch(
            "gfjproxy.providers.gemini_cli.gemini_cli_load_project_id"
        )
        mock_load_project_id_result = mocker.Mock()
        mock_load_project_id_result.success = True
        mock_load_project_id_result.value = "xyz"
        mock_load_project_id.return_value = mock_load_project_id_result

    user = UserSettings(storage, XUID("test", "user"))

    commands = []
    jai_req = JaiRequest(
        api_key=f"{provider}/test-key",
        models={provider: "test-model"},
        messages=[],
        quiet=True,
        quiet_commands=True,
    )

    for k, v in advsettings.items():
        commands.append(f"//advset_{k} this\n")
        setattr(jai_req, k, v)

    jai_req.messages.append(
        JaiMessage.parse({"content": "".join(commands), "role": "user"})
    )

    handle_chat_message(user, jai_req, ResponseHelper())

    mock_call.assert_called_once()
    _, kwargs = mock_call.call_args

    if provider == "google":
        json_body = kwargs["config"]
    elif provider == "gemini_cli":
        json_body = kwargs["json"]["request"]["generationConfig"]
    else:
        json_body = kwargs["json"]

    for k in ADVSETTINGS:
        v = advsettings.get(k)

        if k == "repetition_penalty":
            k = "presence_penalty"

        if provider == "gemini_cli":
            # Convert from snake_case to camelCase
            k = "".join((w.title() if i > 0 else w) for i, w in enumerate(k.split("_")))

        if v is not None:
            assert k in json_body
            assert json_body[k] == pytest.approx(v)
        else:
            assert k not in json_body
