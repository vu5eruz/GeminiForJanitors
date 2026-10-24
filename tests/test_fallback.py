from typing import Any

import httpx2
import pytest
from httpx2 import ReadTimeout
from pytest_mock import MockerFixture

from gfjproxy.handlers import (
    _fallback_chain,
    _should_fallback,
    handle_chat_message,
)
from gfjproxy.models import JaiMessage, JaiRequest, JaiResult
from gfjproxy.utils import ResponseHelper
from gfjproxy.xuiduser import XUID, LocalUserStorage, UserSettings

################################################################################

API_KEY = "AIzaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

CHAIN = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]


def make_mock_response(text: str) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def make_http_error(code: int, status: str, message: str) -> httpx2.HTTPStatusError:
    req = httpx2.Request("POST", "https://generativelanguage.googleapis.com/")
    resp = httpx2.Response(
        code,
        json={"error": {"code": code, "message": message, "status": status}},
        request=req,
    )
    return httpx2.HTTPStatusError(f"HTTP {code}", request=req, response=resp)


def make_blocked_response() -> dict[str, Any]:
    return {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]}


RATE_LIMITED = make_http_error(
    429, "RESOURCE_EXHAUSTED", "You exceeded your current quota"
)

OVERLOADED = make_http_error(503, "UNAVAILABLE", "The model is overloaded")

BAD_KEY = make_http_error(400, "INVALID_ARGUMENT", "API key not valid")


def run_chat(
    mocker: MockerFixture,
    side_effects: list[Any],
    *,
    fallback: list[str] | None = None,
    saved_fallback: list[str] | None = None,
    message: str = "Hello",
) -> tuple[ResponseHelper, Any]:
    """Runs a chat message with one mocked provider response per attempt."""

    mock_post = mocker.patch("gfjproxy.providers.gemini.http_client.post")

    responses = []
    for effect in side_effects:
        if isinstance(effect, Exception):
            responses.append(effect)
            continue
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = effect
        mock_response.raise_for_status.return_value = None
        responses.append(mock_response)

    mock_post.side_effect = responses

    user = UserSettings(LocalUserStorage(), XUID("john", "smith"))
    if saved_fallback is not None:
        user.fallback = saved_fallback

    jai_req = JaiRequest(
        api_key=API_KEY,
        models={"google": "gemini-2.5-flash"},
        quiet=True,
        quiet_commands=True,
        messages=[JaiMessage.parse({"role": "user", "content": message})],
    )
    if fallback is not None:
        jai_req.fallback = fallback

    response = handle_chat_message(user, jai_req, ResponseHelper())

    return response, mock_post


################################################################################


def test_should_fallback_on_transient_errors():
    assert _should_fallback(JaiResult(504, "Gateway Timeout"))
    assert _should_fallback(JaiResult(503, "Overloaded"))
    assert _should_fallback(JaiResult(429, "Quota"))
    assert _should_fallback(JaiResult(502, "Response blocked/empty due to SAFETY."))


def test_should_not_fallback_on_user_errors():
    assert not _should_fallback(JaiResult(400, "API key not valid"))
    assert not _should_fallback(JaiResult(401, "Unauthorized"))
    assert not _should_fallback(JaiResult(404, "Invalid/unsupported model"))


def test_chain_keeps_order_and_drops_other_providers():
    provider, chain = _fallback_chain(
        API_KEY,
        [
            "gemini-3.8-flash",
            "deepseek-chat",  # different provider, must be dropped
            "gemini-3.7-flash",
            "gemini-3.8-flash",  # duplicate, must be dropped
        ],
    )
    assert provider == "google"
    assert chain == ["gemini-3.8-flash", "gemini-3.7-flash"]


def test_chain_empty_without_fallback():
    assert _fallback_chain(API_KEY, []) == ("", [])


################################################################################


def test_first_model_answers_without_a_note(mocker: MockerFixture):
    response, mock_post = run_chat(
        mocker,
        [make_mock_response("Bot response.")],
        fallback=CHAIN,
    )

    assert response.status == 200
    assert response.message == "Bot response."
    assert mock_post.call_count == 1


def test_falls_back_to_second_model(mocker: MockerFixture):
    response, mock_post = run_chat(
        mocker,
        [ReadTimeout(""), make_mock_response("Bot response.")],
        fallback=CHAIN,
    )

    assert response.status == 200
    assert mock_post.call_count == 2
    assert "Bot response." in response.message
    assert "gemini-3.8-flash" in response.message
    assert "gemini-3.7-flash" in response.message

    # The second model must be the one that was actually asked
    assert "gemini-3.7-flash" in mock_post.call_args_list[1].args[0]


def test_falls_back_twice_to_the_last_model(mocker: MockerFixture):
    response, mock_post = run_chat(
        mocker,
        [RATE_LIMITED, OVERLOADED, make_mock_response("Bot response.")],
        fallback=CHAIN,
    )

    assert response.status == 200
    assert mock_post.call_count == 3
    assert "gemini-3.6-flash" in mock_post.call_args_list[2].args[0]


def test_falls_back_on_blocked_response(mocker: MockerFixture):
    response, mock_post = run_chat(
        mocker,
        [make_blocked_response(), make_mock_response("Bot response.")],
        fallback=CHAIN,
    )

    assert response.status == 200
    assert mock_post.call_count == 2


def test_all_models_failing_asks_to_try_again(mocker: MockerFixture):
    response, mock_post = run_chat(
        mocker,
        [RATE_LIMITED, OVERLOADED, ReadTimeout("")],
        fallback=CHAIN,
    )

    assert response.status != 200
    assert mock_post.call_count == 3
    assert "Please try again." in response.message
    for model in CHAIN:
        assert model in response.message


def test_user_errors_stop_the_chain(mocker: MockerFixture):
    response, mock_post = run_chat(
        mocker,
        [BAD_KEY, make_mock_response("Never reached.")],
        fallback=CHAIN,
    )

    assert response.status == 400
    assert mock_post.call_count == 1


def test_saved_chain_is_applied_without_a_command(mocker: MockerFixture):
    response, mock_post = run_chat(
        mocker,
        [ReadTimeout(""), make_mock_response("Bot response.")],
        saved_fallback=CHAIN,
    )

    assert response.status == 200
    assert mock_post.call_count == 2


def test_no_chain_means_a_single_attempt(mocker: MockerFixture):
    response, mock_post = run_chat(
        mocker,
        [ReadTimeout(""), make_mock_response("Never reached.")],
    )

    assert response.status == 504
    assert mock_post.call_count == 1


################################################################################


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("//fallback gemini-3.8-flash, gemini-3.7-flash", CHAIN[:2]),
        ("//fallback gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash", CHAIN),
        ("//fallback GEMINI-3.8-FLASH, Gemini-3.7-Flash", CHAIN[:2]),
        ("Hi //fallback gemini-3.8-flash, gemini-3.7-flash", CHAIN[:2]),
    ],
)
def test_fallback_command_sets_the_chain(message: str, expected: list[str]):
    commands, _ = JaiMessage.parse({"role": "user", "content": message}).commands, None

    user = UserSettings(LocalUserStorage(), XUID("john", "smith"))
    jai_req = JaiRequest(quiet_commands=True)
    response = ResponseHelper()

    assert len(commands) == 1
    commands[0](user, jai_req, response)

    assert user.fallback == expected
    assert jai_req.fallback == expected


def test_fallback_command_off_clears_the_chain():
    user = UserSettings(LocalUserStorage(), XUID("john", "smith"))
    user.fallback = CHAIN

    message = JaiMessage.parse({"role": "user", "content": "//fallback off"})
    jai_req = JaiRequest(quiet_commands=True)

    message.commands[0](user, jai_req, ResponseHelper())

    assert user.fallback == []
    assert jai_req.fallback == []


def test_fallback_command_does_not_eat_the_message():
    message = JaiMessage.parse(
        {
            "role": "user",
            "content": "//fallback gemini-3.8-flash, gemini-3.7-flash\nHello there",
        }
    )

    assert message.commands[0].args == "gemini-3.8-flash, gemini-3.7-flash"
    assert message.content.strip() == "Hello there"


def test_fallback_command_rejects_a_single_model():
    from gfjproxy.commands import CommandError

    message = JaiMessage.parse(
        {"role": "user", "content": "//fallback gemini-3.8-flash"}
    )
    jai_req = JaiRequest(quiet_commands=True)

    with pytest.raises(CommandError):
        message.commands[0](
            UserSettings(LocalUserStorage(), XUID("john", "smith")),
            jai_req,
            ResponseHelper(),
        )
