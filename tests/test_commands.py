import pytest

from gfjproxy.commands import Command, parse_message, strip_message

################################################################################

# Input message, output message, commands
SAMPLE_PARSED_MESSAGES = [
    # No commands to parse
    ("Hello, World!", "Hello, World!", []),
    # Single commands
    ("//banner", "", [Command("banner")]),  # This one requires no argument
    ("//nobot on", "", [Command("nobot", "on")]),
    ("//prefill on", "", [Command("prefill", "on")]),
    ("//squash on", "", [Command("squash", "on")]),
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


def test_strip_message_basic():
    """Basic processing of model messages."""

    # Don't alter simple messages
    assert strip_message("Hello, World!") == "Hello, World!"

    # Strip leading/trailing lines
    assert strip_message("Hello, World!\n") == "Hello, World!"
    assert strip_message("\nHello, World!") == "Hello, World!"
    assert strip_message("\nHello, World!\n") == "Hello, World!"

    # Remove leading/trailing white space around simple messages
    assert strip_message("  abcdef") == "abcdef"
    assert strip_message("abcdef  ") == "abcdef"
    assert strip_message("  abcdef  ") == "abcdef"

    # Preserve markdown list indentations but still strip trailing white space
    assert strip_message("- The ") == "- The"
    assert strip_message("  - quick ") == "  - quick"
    assert strip_message("     - brown ") == "     - brown"
    assert strip_message("       - fox") == "       - fox"
    assert strip_message("* Jumps ") == "* Jumps"
    assert strip_message("  * over ") == "  * over"
    assert strip_message("     * lazy") == "     * lazy"
    assert strip_message("       * dog") == "       * dog"

    # Coalesce spaces between words
    assert strip_message("a b c") == "a b c"
    assert strip_message("a   b   c") == "a b c"
    assert strip_message("   a   b     c ") == "a b c"

    # Coalesce spaces between list markers and content
    assert strip_message("- Lorem") == "- Lorem"
    assert strip_message("  -   Ipsum") == "  - Ipsum"
    assert strip_message("* Lorem") == "* Lorem"
    assert strip_message("  *   Ipsum") == "  * Ipsum"

    # Do not coalesce consecutive empty lines together
    assert strip_message("A\nB\nC") == "A\nB\nC"
    assert strip_message("A\n\nB\nC") == "A\n\nB\nC"
    assert strip_message("A\n\nB\n\n\nC") == "A\n\nB\n\n\nC"

    # Remove leading/trailing white space per line
    assert strip_message("  A\nB  \n  C  ") == "A\nB\nC"


def test_strip_message_proxy():
    """Removing <proxy></proxy> and its content from proxy messages."""

    # Whole message comes from proxy
    assert strip_message("<proxy>Lorem Ipsum</proxy>") == ""

    # Handle leading/trailing model messages
    assert strip_message("AAA<proxy>XXX</proxy>") == "AAA"
    assert strip_message("<proxy>XXX</proxy>BBB") == "BBB"
    assert strip_message("AAA<proxy>XXX</proxy>BBB") == "AAABBB"

    # Handle model messages sandwiched in between proxy messages
    assert strip_message("<proxy>XXX</proxy>ABC<proxy>YYY</proxy>") == "ABC"

    # Handle proxy messages that span across multiple lines
    assert strip_message("ABCDEF<proxy>XXX\nYYY</proxy>") == "ABCDEF"
    assert strip_message("<proxy>XXX\nYYY</proxy>ABCDEF") == "ABCDEF"
    assert strip_message("ABC<proxy>XXX\nYYY</proxy>DEF") == "ABCDEF"

    # Handle multiple multi-line proxy messages
    assert (
        strip_message(
            "111<proxy>XXX\nYYY</proxy>\n"
            + "<proxy>XXX\nYYY</proxy>222\n"
            + "333<proxy>XXX\nYYY</proxy>444"
        )
        == "111\n222\n333444"
    )


################################################################################
