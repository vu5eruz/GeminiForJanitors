import pytest

from gfjproxy.providers.gemini import THINKING_LEVEL, build_generation_config

SETTINGS = {
    "temperature": 0.9,
    "top_k": 40,
    "top_p": 0.95,
    "max_tokens": 2048,
    "frequency_penalty": 0.5,
    "repetition_penalty": 0.25,
}


@pytest.mark.parametrize(
    "model",
    [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
        "gemini-4-argon",
    ],
)
def test_modern_models_use_thinking_level(model: str):
    config = build_generation_config(model, SETTINGS)

    assert config["thinkingConfig"] == {"thinkingLevel": THINKING_LEVEL}
    assert THINKING_LEVEL == "MEDIUM"
    for deprecated in ("temperature", "topK", "topP"):
        assert deprecated not in config
    assert config["maxOutputTokens"] == 2048
    assert config["frequencyPenalty"] == 0.5
    assert config["presencePenalty"] == 0.25


def test_flash_lite_31_keeps_default_thinking():
    config = build_generation_config("gemini-3.1-flash-lite", SETTINGS)

    assert "thinkingConfig" not in config
    assert "temperature" not in config


@pytest.mark.parametrize("model", ["gemini-2.5-flash", "gemma-3-27b-it", "test-model"])
def test_older_models_keep_sampling(model: str):
    config = build_generation_config(model, SETTINGS)

    assert "thinkingConfig" not in config
    assert config["temperature"] == 0.9
    assert config["topK"] == 40
    assert config["topP"] == 0.95


def test_no_settings():
    assert build_generation_config("gemini-2.5-flash", None) == {}
    assert build_generation_config("gemini-3.8-flash", None) == {
        "thinkingConfig": {"thinkingLevel": "MEDIUM"}
    }


def test_non_json_error_page_does_not_crash(mocker):
    import httpx2

    from gfjproxy.models import JaiMessage
    from gfjproxy.providers.gemini import gemini_generate_content
    from gfjproxy.xuiduser import XUID

    request = httpx2.Request("POST", "https://example.com")
    response = httpx2.Response(502, text="<html>Bad Gateway</html>", request=request)
    mocker.patch("gfjproxy.providers.gemini.http_client.post", return_value=response)

    result = gemini_generate_content(
        XUID("test", "user"), "key", "gemini-3.8-flash", [JaiMessage(content="hi")]
    )

    assert result.status == 502
    assert "Bad Gateway" in result.error


def test_grounding_links_deduplicated(mocker):
    from gfjproxy.providers import gemini
    from gfjproxy.xuiduser import XUID

    mocker.patch.object(
        gemini, "_resolve_link", side_effect=lambda _u, link: link.upper()
    )
    links = gemini._resolve_links(XUID("test", "user"), ["a", "b", "a", "c"])

    assert links == ["A", "B", "C"]
