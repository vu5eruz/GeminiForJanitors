from gfjproxy.utils import ResponseHelper, is_proxy_test

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


def test_response_helper():
    """Usage test."""

    def make_jai_res_str(*content):
        content = repr("\n".join(content))[1:-1]
        return [
            '{"choices": [{"index": 0, "message": {"role": "assistant", "content": "'
            + content
            + '"}, "finish_reason": "stop"}]}'
        ]

    # Basic error responses (Google AI or something returned an error)
    # ----------------------------------------------------------------

    assert (  # Ensure the status_code is preserved
        ResponseHelper().build_error("Lorem Ipsum", 400).status_code == 400
    )

    assert (  # Chat response error (JanitorAI will prepend "PROXY ERROR")
        ResponseHelper().build_error("Lorem Ipsum", 400).response == ["Lorem Ipsum"]
    )

    assert (  # Proxy test error (JanitorAI shows this error message unaltered)
        ResponseHelper(wrap_errors=True)
        .build_error("Lorem Ipsum", 400)
        .response  # flask.Response
        == ['{"error": "PROXY ERROR 400: Lorem Ipsum"}']
    )

    # Basic chat responses (successful responses from Google AI)
    # ----------------------------------------------------------

    assert (  # Ensure the status_code is 200 for JanitorAI to accept the message
        ResponseHelper().build_message("Hello, World!").status_code == 200
    )

    assert (  # Ensure the model's output is unaltered in this case
        ResponseHelper().add_message("Hello, World!").message == "Hello, World!"
    )

    assert (  # Don't strip white space in this case
        ResponseHelper().add_message("  \nZXY  \n").message == "  \nZXY  \n"
    )

    assert (  # Ensure the result is in the valid JanitorAI response format
        ResponseHelper().build_message("abcdef").response == make_jai_res_str("abcdef")
    )

    assert (  # wrap_errors should NOT have an effect on this
        ResponseHelper(wrap_errors=True).build_message("abcdef").response
        == make_jai_res_str("abcdef")
    )

    assert (  # Ensure support for joining multiple bot messages together
        ResponseHelper().add_message("Hello, World!", "Lorem Ipsum").message
        == "Hello, World!\nLorem Ipsum"
    )

    assert (  # Multiple bot messages should not affect the final result
        ResponseHelper()
        .build_message("Hello, World!", "Lorem Ipsum")
        .response  # flask.Response
        == make_jai_res_str("Hello, World!", "Lorem Ipsum")
    )

    # Basic proxy chat responses (non-inline command output from proxy)
    # -----------------------------------------------------------------

    assert (  # Ensure the status_code is 200 for JanitorAI to accept the message
        ResponseHelper().add_proxy_message("Hello, World!").build().status_code == 200
    )

    assert (  # Ensure a message is wrapped within <proxy> tags
        ResponseHelper().add_proxy_message("Hello, World!").message
        == "<proxy>Hello, World!\n</proxy>"
    )

    assert (  # Join multiple proxy messages together
        ResponseHelper()
        .add_proxy_message("abc")
        .add_proxy_message("def")
        .add_proxy_message("ghi")
        .message
        == "<proxy>abc\ndef\nghi\n</proxy>"
    )

    assert (  # Ensure the result is in the valid JanitorAI response format
        ResponseHelper()
        .add_proxy_message("abc")
        .add_proxy_message("def")
        .add_proxy_message("ghi")
        .build()
        .response  # flask.Response
        == make_jai_res_str("<proxy>abc", "def", "ghi", "</proxy>")
    )

    # Complex multi-line chat responses (command output and bot responses)
    # --------------------------------------------------------------------

    assert (  # Ensure a proxy message in prefix position works
        ResponseHelper().add_proxy_message("abc").add_message("def").message
        == "<proxy>abc\n</proxy>def"
    )

    assert (  # Ensure a proxy message in suffix position works
        ResponseHelper().add_message("abc").add_proxy_message("def").message
        == "abc\n<proxy>def\n</proxy>"
    )

    assert (  # Ensure a proxy message can be sandwiched between bot responses
        ResponseHelper()
        .add_message("abc")
        .add_proxy_message("def")
        .add_message("ghi")
        .message
        == "abc\n<proxy>def\n</proxy>ghi"
    )

    assert (  # Ensure proxy messages coalesce
        ResponseHelper()
        .add_message("abc")
        .add_proxy_message("lorem")
        .add_proxy_message("ipsum")
        .add_message("def")
        .message
        == "abc\n<proxy>lorem\nipsum\n</proxy>def"
    )

    assert (  # Ensure proxy messages can be interleaved with bot responses
        ResponseHelper()
        .add_message("A")
        .add_proxy_message("B")
        .add_message("C")
        .add_proxy_message("D")
        .message
        == "A\n<proxy>B\n</proxy>C\n<proxy>D\n</proxy>"
    )

    # Complex multi-line chat responses (chat, error and proxy)
    # ---------------------------------------------------------

    assert (  # Ensure errors are wrapped like proxy messages
        ResponseHelper()
        .add_message("abc")
        .add_error("lol", 404)
        .add_message("ghi")
        .message
        == "abc\n<proxy>Error 404: lol\n</proxy>ghi"
    )

    assert (  # Ensure errors and proxy coalesce together
        ResponseHelper()
        .add_message("abc")
        .add_error("lol", 404)
        .add_proxy_message("kek")
        .add_message("ghi")
        .message
        == "abc\n<proxy>Error 404: lol\nkek\n</proxy>ghi"
    )

    assert (  # Test all features at once
        ResponseHelper()
        .add_message("  Bot reply with leading spaces")
        .add_proxy_message("Proxy banner")
        .add_error("Proxy had an error", 500)
        .add_message("This comes after the closing tag")
        .add_message("Bot reply with trailing spaces  ")
        .add_proxy_message("More proxy banner")
        .add_error("Proxy had another error", 502)
        .build()
        .response  # flask.Response
        == make_jai_res_str(
            "  Bot reply with leading spaces",
            "<proxy>Proxy banner",
            "Error 500: Proxy had an error",
            "</proxy>This comes after the closing tag",
            "Bot reply with trailing spaces  ",
            "<proxy>More proxy banner",
            "Error 502: Proxy had another error",
            "</proxy>",
        )
    )


################################################################################
