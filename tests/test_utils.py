from gfjproxy.utils import is_proxy_test

################################################################################

SAMPLE_NORMAL_CHAT_JSON = {
    "messages": [
        {
            "content": "Bot description.\n<UserPersona>User persona description</UserPersona>\n<example_dialogs>Blah blah blah</example_dialogs>\n",
            "role": "system",
        },
        {"content": ".", "role": "user"},
        {"content": "Bot initial message", "role": "assistant"},
        {"content": "User persona: inital message", "role": "user"},
        {"content": "Bot reply", "role": "assistant"},
    ],
    "model": "gemini-2.5-pro",
    "stream": False,
    "temperature": 0.8,
}

SAMPLE_PROXY_TEST_JSON = {
    "max_tokens": 10,
    "messages": [{"content": "Just say TEST", "role": "user"}],
    "model": "gemini-2.5-pro",
    "temperature": 0,
}


def test_is_proxy_test():
    """Basic parsing tests."""

    assert is_proxy_test(SAMPLE_PROXY_TEST_JSON)

    assert not is_proxy_test(SAMPLE_NORMAL_CHAT_JSON)


################################################################################
