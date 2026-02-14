from typing import Any

import pytest
from google.genai import errors, types
from httpx import ReadTimeout
from pytest_mock import MockerFixture

from gfjproxy._globals import BANNER, BANNER_VERSION
from gfjproxy.handlers import handle_chat_message, handle_proxy_test
from gfjproxy.models import JaiMessage, JaiRequest
from gfjproxy.utils import ResponseHelper
from gfjproxy.xuiduser import XUID, LocalUserStorage, UserSettings

################################################################################


def make_mock_response(text):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.ModelContent(parts=[types.Part(text=text)]))
        ]
    )


################################################################################

# Any of these errors could occur during proxy test and chat message.
# Thus, that are to be tested on both handlers.

COMMON_ERRORS = [
    {
        "generate_content_mock": ReadTimeout(""),
        "expected_result": ("Gateway Timeout", 504),
    },
    {
        "generate_content_mock": errors.APIError(
            code=418,
            response_json={
                "message": "I'm a teapot",
                "status": "TEAPOT",
            },
        ),
        "expected_result": ("Unhanded exception from Google AI.", 502),
    },
    {
        "generate_content_mock": errors.ClientError(
            code=400,
            response_json={
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
            },
        ),
        "expected_result": ("API key not valid. Please pass a valid API key.", 400),
    },
    {
        "generate_content_mock": errors.ClientError(
            code=429,
            response_json={
                "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits.",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {
                                "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                                "quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
                                "quotaDimensions": {
                                    "model": "gemini-2.5-pro",
                                    "location": "global",
                                },
                                "quotaValue": "2",
                            },
                        ],
                    },
                ],
            },
        ),
        "expected_result": ("Requests per Minute quota exceeded.", 429),
    },
    {
        "generate_content_mock": errors.ClientError(
            code=429,
            response_json={
                "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits.",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {
                                "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                                "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                                "quotaDimensions": {
                                    "location": "global",
                                    "model": "gemini-2.5-pro",
                                },
                                "quotaValue": "50",
                            }
                        ],
                    },
                ],
            },
        ),
        "expected_result": ("Requests per Day quota exceeded.", 429),
    },
    {
        "generate_content_mock": errors.ClientError(
            code=403,
            response_json={
                "message": "Generative Language API has not been used in project * before or it is disabled. Enable it by visiting https://console.developers.google.com/apis/api/generativelanguage.googleapis.com/overview?project=182995638091 then retry. If you enabled this API recently, wait a few minutes for the action to propagate to our systems and retry.",
                "status": "PERMISSION_DENIED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "SERVICE_DISABLED",
                        "domain": "googleapis.com",
                        "metadata": {
                            "activationUrl": "https://console.developers.google.com/apis/api/generativelanguage.googleapis.com/overview?project=182995638091",
                            "service": "generativelanguage.googleapis.com",
                            "serviceTitle": "Generative Language API",
                            "containerInfo": "*",
                            "consumer": "projects/*",
                        },
                    },
                ],
            },
        ),
        "expected_result": ("Generative Language API needs to be enabled", 403),
    },
    {
        "generate_content_mock": errors.ClientError(
            code=403,
            response_json={
                "message": "Permission denied: Consumer 'api_key:*' has been suspended.",
                "status": "PERMISSION_DENIED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "CONSUMER_SUSPENDED",
                        "domain": "googleapis.com",
                        "metadata": {
                            "service": "generativelanguage.googleapis.com",
                            "containerInfo": "api_key:*",
                            "consumer": "projects/*",
                        },
                    },
                ],
            },
        ),
        "expected_result": ("Customer suspended. You might be banned.", 403),
    },
    {
        "generate_content_mock": errors.ServerError(
            code=500,
            response_json={
                "message": "Some internal error.",
                "status": "INTERNAL",
            },
        ),
        "expected_result": ("Google AI had an internal error. Try again later.", 500),
    },
    {
        "generate_content_mock": errors.ServerError(
            code=503,
            response_json={
                "message": "The model is overloaded. Please try again later.",
                "status": "UNAVAILABLE",
            },
        ),
        "expected_result": ("The model is overloaded. Please try again later.", 503),
    },
]

################################################################################

PROXY_TESTS = [
    {
        "generate_content_mock": make_mock_response("TEST"),
        "expected_result": ("TEST", 200),
    },
]


@pytest.mark.parametrize(
    "params",
    COMMON_ERRORS + PROXY_TESTS,
)
def test_proxy_test(mocker: MockerFixture, params: dict[str, Any]):
    generate_content_mock = params["generate_content_mock"]
    expected_message, expected_status = params["expected_result"]

    mock_client_class = mocker.patch("gfjproxy.handlers.genai.Client")
    mock_instance = mock_client_class.return_value
    if isinstance(generate_content_mock, Exception):
        mock_instance.models.generate_content.side_effect = generate_content_mock
    else:
        mock_instance.models.generate_content.return_value = generate_content_mock

    storage = LocalUserStorage()
    xuid = XUID("john", "smith")
    user = UserSettings(storage, xuid)

    jai_req = JaiRequest()

    response = handle_proxy_test(user, jai_req, ResponseHelper(wrap_errors=True))

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


CHAT_MESSAGE_TESTS = [
    {  # Blank-slate users should get the bot response plus the latest banner
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.\n" + BANNER, 200),
        "extra_settings": [],
    },
    {  # Blank-slate users on /quiet/ should not see any banner
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.", 200),
        "extra_settings": [
            ("jai_req_quiet", True),
        ],
    },
    {  # Users that already saw the latest banner should not see it again
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.", 200),
        "extra_settings": [
            ("call_do_show_banner", BANNER_VERSION),
        ],
    },
    {  # Users that saw a different banner should see the newest one
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.\n" + BANNER, 200),
        "extra_settings": [
            ("call_do_show_banner", BANNER_VERSION - 1),
        ],
    },
    {  # Ensure the //prefill command has an actual effect on the prompt
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "//prefill this Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
        ],
        "extra_after_tests": [("look_for_prefill_in_contents", True)],
    },
    {  # //think should not alter "plain" response
        "generate_content_mock": make_mock_response("ABC XYZ"),
        "expected_result": ("ABC XYZ", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "//think this Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
        ],
    },
    {  # //think should handle the ideal case and extract only the response
        "generate_content_mock": make_mock_response(
            "<think>ABC</think><response>XYZ</response>"
        ),
        "expected_result": ("XYZ", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "//think this Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
        ],
    },
    {  # //think ideal case but out of order
        "generate_content_mock": make_mock_response(
            "<response>XYZ</response><think>ABC</think>"
        ),
        "expected_result": ("XYZ", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "//think this Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
        ],
    },
    {  # //think should remove any thinking while leaving everything else intact
        "generate_content_mock": make_mock_response("123<think>ABC</think>XYZ"),
        "expected_result": ("123XYZ", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "//think this Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
        ],
    },
    {  # //think should recover the bot's response if it was correctly wrapped in tags
        "generate_content_mock": make_mock_response("ABC<response>XYZ</response>DEF"),
        "expected_result": ("XYZ", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "//think this Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
        ],
    },
    {  # //think should extract everything after a lone response
        "generate_content_mock": make_mock_response("ABC<response>XYZ"),
        "expected_result": ("XYZ", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "//think this Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
        ],
    },
    {  # //think should remove everything before a lone think
        "generate_content_mock": make_mock_response("ABC</think>XYZ"),
        "expected_result": ("XYZ", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "//think this Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
        ],
    },
    {  # //think given a lone think and response in order, recover response
        "generate_content_mock": make_mock_response("ABC</think><response>XYZ"),
        "expected_result": ("XYZ", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "//think this Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
        ],
    },
    {  # Handle rejections (case 1)
        "generate_content_mock": types.GenerateContentResponse(
            prompt_feedback=types.GenerateContentResponsePromptFeedback(
                block_reason=types.BlockedReason.SAFETY,
            ),
        ),
        "expected_result": (
            "Response blocked/empty due to SAFETY."
            + "\nTry using: `//ooctrick on`, `//prefill on`, `//think on`",
            502,
        ),
    },
    {  # Handle rejections (case 2)
        "generate_content_mock": types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    finish_reason=types.FinishReason.RECITATION,
                )
            ],
        ),
        "expected_result": (
            "Response blocked/empty due to RECITATION."
            + "\nTry using: `//ooctrick on`, `//prefill on`, `//think on`",
            502,
        ),
    },
    {  # Ensure user set temperature is honored
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse({"role": "user", "content": "Message"}),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
            ("jai_req_temperature", 1.2345),
        ],
        "extra_after_tests": [("assert_temperature_value", 1.2345)],
    },
    {  # Ensure the //advsettings command has an actual effect on generation settings
        "generate_content_mock": make_mock_response("Bot response."),
        "expected_result": ("Bot response.", 200),
        "extra_settings": [
            (
                "jai_add_message",
                JaiMessage.parse(
                    {"role": "user", "content": "//advsettings this Message"}
                ),
            ),
            ("jai_req_quiet", True),
            ("jai_req_quiet_commands", True),
            ("jai_req_max_tokens", 69),
            ("jai_req_top_k", 50),
            ("jai_req_top_p", 0.95),
            ("jai_req_repetition_penalty", 0.99),
            ("jai_req_frequency_penalty", 0.90),
        ],
        "extra_after_tests": [
            ("assert_max_tokens_value", 69),
            ("assert_top_k_value", 50),
            ("assert_top_p_value", 0.95),
            ("assert_repetition_penalty_value", 0.99),
            ("assert_frequency_penalty_value", 0.90),
        ],
    },
]


@pytest.mark.parametrize(
    "params",
    COMMON_ERRORS + CHAT_MESSAGE_TESTS,
)
def test_chat_message(mocker: MockerFixture, params: dict[str, Any]):
    generate_content_mock = params["generate_content_mock"]
    expected_message, expected_status = params["expected_result"]
    user_messages = params.get("user_messages", [JaiMessage()])
    extra_settings = params.get("extra_settings", [])
    extra_after_tests = params.get("extra_after_tests", [])

    mock_client_class = mocker.patch("gfjproxy.handlers.genai.Client")
    mock_instance = mock_client_class.return_value
    if isinstance(generate_content_mock, Exception):
        mock_instance.models.generate_content.side_effect = generate_content_mock
    else:
        mock_instance.models.generate_content.return_value = generate_content_mock

    user = UserSettings(LocalUserStorage(), XUID("john", "smith"))

    jai_req = JaiRequest(messages=user_messages)

    for key, value in extra_settings:
        if key == "call_do_show_banner":
            user.do_show_banner(value)
        elif key == "jai_add_message":
            jai_req.messages.append(value)
        elif key == "jai_req_quiet":
            jai_req.quiet = value
        elif key == "jai_req_quiet_commands":
            jai_req.quiet_commands = value
        elif key == "jai_req_temperature":
            jai_req.temperature = value
        elif key == "jai_req_max_tokens":
            jai_req.max_tokens = value
        elif key == "jai_req_top_k":
            jai_req.top_k = value
        elif key == "jai_req_top_p":
            jai_req.top_p = value
        elif key == "jai_req_repetition_penalty":
            jai_req.repetition_penalty = value
        elif key == "jai_req_frequency_penalty":
            jai_req.frequency_penalty = value
        else:
            assert 0, f"Invalid extra_settings key: {key}"

    response = handle_chat_message(user, jai_req, ResponseHelper(wrap_errors=False))

    assert (response.message, response.status) == (
        expected_message,
        expected_status,
    )

    _, kwargs = mock_instance.models.generate_content.call_args
    gemini_config = kwargs.get("config", {})

    for key, value in extra_after_tests:
        if key == "look_for_prefill_in_contents":
            for content in kwargs.get("contents", []):
                if "<interaction-config>" in content.parts[0].text:
                    break
            else:
                assert 0, "No prefill found in contents"
        elif key == "assert_temperature_value":
            assert gemini_config.get("temperature") == pytest.approx(value)
        elif key == "assert_max_tokens_value":
            assert gemini_config.get("max_output_tokens") == value
        elif key == "assert_top_k_value":
            assert gemini_config.get("top_k") == value
        elif key == "assert_top_p_value":
            assert gemini_config.get("top_p") == pytest.approx(value)
        elif key == "assert_repetition_penalty_value":
            assert gemini_config.get("presence_penalty") == pytest.approx(value)
        elif key == "assert_frequency_penalty_value":
            assert gemini_config.get("frequency_penalty") == pytest.approx(value)
        else:
            assert 0, f"Invalid extra_after_tests key: {key}"


################################################################################
