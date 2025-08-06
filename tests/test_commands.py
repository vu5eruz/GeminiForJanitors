import pytest

from gfjproxy.commands import Command, parse_message, strip_message
from gfjproxy.utils import ResponseHelper

################################################################################

# Input message, output message, commands
SAMPLE_PARSED_MESSAGES = [
    # No commands to parse
    ("Hello, World!", "Hello, World!", []),
    # Single commands
    ("//banner", "", [Command("banner")]),  # This one requires no argument
    ("//nobot on", "", [Command("nobot", "on")]),
    ("//prefill on", "", [Command("prefill", "on")]),
    # Multiple commands and white space
    ("//banner//banner//banner", "", [Command("banner")] * 3),
    ("//banner //banner //banner", "", [Command("banner")] * 3),
    ("//prefill on//prefill on//prefill on", "", [Command("prefill", "on")] * 3),
    ("//prefill on //prefill on //prefill on", "", [Command("prefill", "on")] * 3),
    # Command in leading/trailing position with user messages
    ("//banner Lorem", "Lorem", [Command("banner")]),
    ("Lorem //banner", "Lorem", [Command("banner")]),
    ("//banner Lorem //banner", "Lorem", [Command("banner")] * 2),
    # Commands interspaced with user messages
    ("//banner Lorem //banner Ipsum //banner", "Lorem Ipsum", [Command("banner")] * 3),
    (
        "//prefill on Lorem //prefill on Ipsum //prefill on",
        "Lorem Ipsum",
        [Command("prefill", "on")] * 3,
    ),
]


@pytest.mark.parametrize("sample", SAMPLE_PARSED_MESSAGES)
def test_parse_message(sample):
    """Command parsing of use messages."""

    input_msg, output_msg, cmd_list = sample

    assert parse_message(input_msg) == (cmd_list, output_msg)


################################################################################


SAMPLE_BASIC_MESSAGE_STRIPPING = [
    # Don't alter simple messages
    ("Hello, World!", "Hello, World!"),
    # Strip leading/trailing lines
    ("Hello, World!\n", "Hello, World!"),
    ("\nHello, World!", "Hello, World!"),
    ("\nHello, World!\n", "Hello, World!"),
    # Remove leading/trailing white space around simple messages
    ("  abcdef", "abcdef"),
    ("abcdef  ", "abcdef"),
    ("  abcdef  ", "abcdef"),
    # Preserve markdown list indentations but still strip trailing white space
    ("- The ", "- The"),
    ("  - quick ", "  - quick"),
    ("     - brown ", "     - brown"),
    ("       - fox", "       - fox"),
    ("* Jumps ", "* Jumps"),
    ("  * over ", "  * over"),
    ("     * lazy", "     * lazy"),
    ("       * dog", "       * dog"),
    # Coalesce spaces between words
    ("a b c", "a b c"),
    ("a   b   c", "a b c"),
    ("   a   b     c ", "a b c"),
    # Coalesce spaces between list markers and content
    ("- Lorem", "- Lorem"),
    ("  -   Ipsum", "  - Ipsum"),
    ("* Lorem", "* Lorem"),
    ("  *   Ipsum", "  * Ipsum"),
    # Do not coalesce consecutive empty lines together
    ("A\nB\nC", "A\nB\nC"),
    ("A\n\nB\nC", "A\n\nB\nC"),
    ("A\n\nB\n\n\nC", "A\n\nB\n\n\nC"),
    # Remove leading/trailing white space per line
    ("  A\nB  \n  C  ", "A\nB\nC"),
]


@pytest.mark.parametrize("sample", SAMPLE_BASIC_MESSAGE_STRIPPING)
def test_strip_message_basic(sample):
    """Basic processing of model messages."""

    input_str, output_str = sample

    assert strip_message(input_str) == output_str


################################################################################

PROXY_OPEN = ResponseHelper.PROXY_TAG_OPEN
PROXY_CLOSE = ResponseHelper.PROXY_TAG_CLOSE

SAMPLE_PROXY_MESSAGE_STRIPPING = [
    # Whole message comes from proxy
    (f"{PROXY_OPEN}Lorem Ipsum{PROXY_CLOSE}", ""),
    # Handle leading/trailing model messages
    (f"AAA{PROXY_OPEN}XXX{PROXY_CLOSE}", "AAA"),
    (f"{PROXY_OPEN}XXX{PROXY_CLOSE}BBB", "BBB"),
    (f"AAA{PROXY_OPEN}XXX{PROXY_CLOSE}BBB", "AAABBB"),
    # Handle model messages sandwiched in between proxy messages
    (f"{PROXY_OPEN}XXX{PROXY_CLOSE}ABC{PROXY_OPEN}YYY{PROXY_CLOSE}", "ABC"),
    # Handle proxy messages that span across multiple lines
    (f"ABCDEF{PROXY_OPEN}XXX\nYYY{PROXY_CLOSE}", "ABCDEF"),
    (f"{PROXY_OPEN}XXX\nYYY{PROXY_CLOSE}ABCDEF", "ABCDEF"),
    (f"ABC{PROXY_OPEN}XXX\nYYY{PROXY_CLOSE}DEF", "ABCDEF"),
    # Handle multiple multi-line proxy messages
    (
        f"111{PROXY_OPEN}XXX\nYYY{PROXY_CLOSE}\n"
        + f"{PROXY_OPEN}XXX\nYYY{PROXY_CLOSE}222\n"
        + f"333{PROXY_OPEN}XXX\nYYY{PROXY_CLOSE}444",
        "111\n222\n333444",
    ),
]


@pytest.mark.parametrize("sample", SAMPLE_PROXY_MESSAGE_STRIPPING)
def test_strip_message_proxy(sample):
    """Removing proxy tags and their content from proxy messages."""

    input_str, output_str = sample

    assert strip_message(input_str) == output_str


################################################################################
