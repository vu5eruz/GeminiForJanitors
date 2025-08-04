import pytest
from httpx import ReadTimeout
from gfjproxy._globals import BANNER, BANNER_VERSION
from gfjproxy.models import JaiRequest
from gfjproxy.handlers import handle_chat_message, handle_proxy_test
from gfjproxy.utils import ResponseHelper
from gfjproxy.xuiduser import LocalUserStorage, UserSettings, XUID
from google import genai
from google.genai import types
from typing import Optional, Union

################################################################################


class MockClientModels:
    """Mock google.genai.Client.models class."""

    def __init__(self, mock):
        self.mock = mock

    def generate_content(
        self,
        *,
        model: str,
        contents: Union[types.ContentListUnion, types.ContentListUnionDict],
        config: Optional[types.GenerateContentConfigOrDict] = None,
    ) -> types.GenerateContentResponse:
        if isinstance(self.mock, Exception):
            raise self.mock
        return self.mock


class MockClient:
    """Mock google.genai.Client class."""

    def __init__(self, mock):
        self.mock = mock

    @property
    def models(self):
        return MockClientModels(self.mock)


def make_mock_response(text):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.ModelContent(parts=[types.Part(text=text)]))
        ]
    )


################################################################################

# Any of these errors could occur during proxy test and chat message.
# Thus, that are to be tested on both handlers.

COMMON_ERRORS = []

COMMON_ERRORS.append(
    {
        "generate_content_mock": ReadTimeout(""),
        "expected_result": ("Gateway Timeout", 504),
    }
)

COMMON_ERRORS.append(
    {
        "generate_content_mock": genai.errors.APIError(
            code=418,
            response_json={
                "message": "I'm a teapot",
                "status": "TEAPOT",
            },
        ),
        "expected_result": ("Unhanded exception from Google AI.", 502),
    }
)

COMMON_ERRORS.append(
    {
        "generate_content_mock": genai.errors.ClientError(
            code=400,
            response_json={
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
            },
        ),
        "expected_result": ("API key not valid. Please pass a valid API key.", 400),
    }
)

COMMON_ERRORS.append(
    {
        "generate_content_mock": genai.errors.ServerError(
            code=500,
            response_json={
                "message": "Some internal error.",
                "status": "INTERNAL",
            },
        ),
        "expected_result": ("Google AI had an internal error.", 502),
    }
)

################################################################################

PROXY_TESTS = []


PROXY_TESTS.append(
    {
        "generate_content_mock": make_mock_response("TEST"),
        "expected_result": ("TEST", 200),
    }
)


@pytest.mark.parametrize(
    "params",
    COMMON_ERRORS + PROXY_TESTS,
)
def test_proxy_test(params):
    generate_content_mock = params["generate_content_mock"]
    expected_message, expected_status = params["expected_result"]

    client = MockClient(generate_content_mock)

    storage = LocalUserStorage()
    xuid = XUID("john", "smith")
    user = UserSettings(storage, xuid)

    jai_req = JaiRequest()

    response = handle_proxy_test(
        client, user, jai_req, ResponseHelper(wrap_errors=True)
    )

    if response.status != 200:
        assert (response.message, response.status) == (
            f"PROXY ERROR {expected_status}: {expected_message}",
            expected_status,
        )
    else:
        assert (response.message, response.status) == (
            expected_message,
            expected_status,
        )


################################################################################


CHAT_MESSAGE_TESTS = []

# Blank-slate users should get the bot response plus the latest banner
CHAT_MESSAGE_TESTS.append(
    {
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.\n" + BANNER, 200),
        "extra_settings": [],
    }
)

# Blank-slate users on /quiet/ should not see any banner
CHAT_MESSAGE_TESTS.append(
    {
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.", 200),
        "extra_settings": [
            ("jai_req_quiet", True),
        ],
    }
)

# Users that already saw the latest banner should not see it again
CHAT_MESSAGE_TESTS.append(
    {
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.", 200),
        "extra_settings": [
            ("call_do_show_banner", BANNER_VERSION),
        ],
    }
)

# Users that saw a different banner should see the newest one
CHAT_MESSAGE_TESTS.append(
    {
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.\n" + BANNER, 200),
        "extra_settings": [
            ("call_do_show_banner", BANNER_VERSION - 1),
        ],
    }
)


@pytest.mark.parametrize(
    "params",
    COMMON_ERRORS + CHAT_MESSAGE_TESTS,
)
def test_chat_message(params):
    generate_content_mock = params["generate_content_mock"]
    expected_message, expected_status = params["expected_result"]

    client = MockClient(generate_content_mock)

    storage = LocalUserStorage()
    xuid = XUID("john", "smith")
    user = UserSettings(storage, xuid)

    jai_req = JaiRequest()

    for key, value in params.get("extra_settings", []):
        if key == "call_do_show_banner":
            user.do_show_banner(value)
        elif key == "jai_req_quiet":
            jai_req.quiet = value
        else:
            assert False  # Invalid extra_settings key

    response = handle_chat_message(
        client, user, jai_req, ResponseHelper(wrap_errors=False)
    )

    assert (response.message, response.status) == (
        expected_message,
        expected_status,
    )


################################################################################
