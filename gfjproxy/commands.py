"""Commands and processing of messages."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from ._globals import PRESETS, BANNER, BANNER_VERSION
from .utils import ResponseHelper

################################################################################


def _stripmultispace(string, *, regex=re.compile(r" +")):
    """Coalesce multiple consecutive spaces into one."""

    return regex.sub(" ", string)


def _stripproxytext(
    string,
    *,
    regex=re.compile(
        re.escape(ResponseHelper.PROXY_TAG_OPEN)
        + r".*?"
        + re.escape(ResponseHelper.PROXY_TAG_CLOSE),
        re.S,
    ),
):
    """Remove <proxy></proxy> tags and their content."""

    return regex.sub("", string)


def _tokenize(string, *, regex=re.compile(r"/+|\w+|\s+|.")):
    """Split a token into '//' or longer, words, white space and punctuation."""

    return (match.group(0) for match in regex.finditer(string))


################################################################################


@dataclass
class Command:
    """User proxy command."""

    # Command name (lowercase, without any leading //)
    name: str

    # Optional command arguments (a single string, must match command argspec)
    args: str = ""

    # Pointer to command function
    func: Callable = field(default=None, repr=False, compare=False, kw_only=True)

    # Prefer to this method instead of directly calling func
    def __call__(self, user, jai_req, response):
        if self.func is None:
            raise RuntimeError(f"Calling {self} without a function pointer")
        return self.func(self.args, user, jai_req, response)


class CommandError(Exception):
    """User error raised by commands."""

    pass


COMMANDS = {}


def command(*, argspec: str = "", **kwargs):
    if argspec:
        regex = re.compile(argspec)

    def outer_wrapper(func):
        cmd_name = func.__name__

        @wraps(func)
        def inner_wrapper(args, user, jai_req, response):
            if argspec and not regex.fullmatch(args):
                if not args:
                    raise CommandError(
                        f'`//{cmd_name}` requires an argument "`{argspec}`".'
                    )
                raise CommandError(
                    f'`//{cmd_name}` only accepts "`{argspec}`", not "`{args}`".'
                )

            if argspec == r"off|on|this" and (setting := kwargs.get("setting")):
                attr = f"use_{setting}"

                if args == "this":
                    setattr(jai_req, attr, True)
                elif args == "on":
                    setattr(jai_req, attr, True)
                    setattr(user, attr, True)
                else:  # "off"
                    setattr(jai_req, attr, False)
                    setattr(user, attr, False)

            return func(args, user, jai_req, response)

        COMMANDS[cmd_name] = {
            "argcount": 1 if argspec else 0,
            "func": inner_wrapper,
        }

        return inner_wrapper

    return outer_wrapper


################################################################################


@command()
def aboutme(args, user, jai_req, response):
    return response.add_proxy_message(
        f"Your user ID on this proxy is `{user.xuid!r}`."
        + f" You were {user.last_seen_msg()}. Your request counter is {user.get_rcounter()}."
        + " Your settings are:",
        f"- //nobot is {'enabled' if user.use_nobot else 'disabled'}",
        f"- //ooctrick is {'enabled' if user.use_ooctrick else 'disabled'}",
        f"- //prefill is {'enabled' if user.use_prefill else 'disabled'}",
        f"- //think is {'enabled' if user.use_think else 'disabled'}",
        f"- //advsettings is {'enabled' if user.use_nobot else 'disabled'}",
    )


@command()
def banner(args, user, jai_req, response):
    user.do_show_banner(BANNER_VERSION)
    return response.add_proxy_message(BANNER, "***")


@command(argspec=r"[A-Za-z]+")
def preset(args, user, jai_req, response):
    if args not in PRESETS:
        raise CommandError(
            f'"`{args}`" is not a valid preset.'
            + " Available presets: "
            + ", ".join(f"`{key}`" for key in PRESETS.keys())
        )

    jai_req.use_preset = PRESETS[args]

    return response.add_proxy_message(f'Added preset "`{args}`" to this message.')


################################################################################

# To add a new "`off|on|this`" command named xyz do the following:
# - Copy-paste any of the commands in here and write your command text
# - Add a "use_xyz" field to models.JaiRequest
# - Add a "use_xyz" getter/setter to xuiduser.UserSettings
# - Implement your commands' additional logic inside handlers._gen_content


@command(argspec=r"off|on|this", setting="advsettings")
def advsettings(args, user, jai_req, response):
    if jai_req.quiet_commands:
        return response
    return response.add_proxy_message(
        f"Advanced generation settings {'enabled' if jai_req.use_advsettings else 'disabled'}"
        + (" (for this message only)." if args == "this" else ".")
    )


@command(argspec=r"off|on|this", setting="nobot")
def nobot(args, user, jai_req, response):
    if jai_req.quiet_commands:
        return response
    return response.add_proxy_message(
        f"Bot description {'omitted' if jai_req.use_nobot else 'kept'}"
        + (" (for this message only)." if args == "this" else ".")
    )


@command(argspec=r"off|on|this", setting="ooctrick")
def ooctrick(args, user, jai_req, response):
    if jai_req.quiet_commands:
        return response
    return response.add_proxy_message(
        f"OOC Trick {'enabled' if jai_req.use_ooctrick else 'disabled'}"
        + (" (for this message only)." if args == "this" else ".")
    )


@command(argspec=r"off|on|this", setting="prefill")
def prefill(args, user, jai_req, response):
    if jai_req.quiet_commands:
        return response
    return response.add_proxy_message(
        f"Prefill {'enabled' if jai_req.use_prefill else 'disabled'}"
        + (" (for this message only)." if args == "this" else ".")
    )


@command(argspec=r"off|on|this", setting="think")
def think(args, user, jai_req, response):
    if jai_req.quiet_commands:
        return response
    return response.add_proxy_message(
        f"Thinking {'enabled' if jai_req.use_think else 'disabled'}"
        + (" (for this message only)." if args == "this" else ".")
    )


################################################################################


def parse_message(message: str) -> tuple[list[Command], str]:
    """Parse an message into a list of commands and the message's content."""

    message = message.strip()

    if "//" not in message:
        # No commands to parse
        return [], _stripmultispace(message)

    commands = []
    content = []

    cmd_argcount = 0
    prev_token = ""
    for token in _tokenize(message):
        if not cmd_argcount:
            if prev_token.startswith("//") and (cmd := COMMANDS.get(token.lower())):
                cmd_argcount = cmd["argcount"]
                commands.append(Command(token, func=cmd["func"]))
                content.pop()  # Remove "//" token
            else:
                content.append(token)
        elif token.isspace():
            continue  # Skip white space between a command and its arguments
        elif token.isalnum():
            cmd_argcount -= 1
            commands[-1].args += token  # Valid argument
        else:
            # Invalid token means there was no valid or not enough arguments
            cmd_argcount = 0  # Stop parsing
            content.append(token)  # Add the token as if there wasn't a command
            # The command function will show the appropriate error to the user

        prev_token = token

    return commands, _stripmultispace("".join(content).strip())


################################################################################


def strip_message(message: str) -> str:
    """Clean up the text of a message, meant for model's output."""

    message = _stripproxytext(message.strip("\n")).split("\n")

    if not message:
        return ""

    result = []

    for line in message:
        index = max(line.find("-"), line.find("*"))
        if index != -1 and line[:index].isspace():
            line = line.rstrip()
            is_list = True
        else:
            line = line.strip()
            is_list = False

        if is_list:
            line = line[:index] + _stripmultispace(line[index:])
        else:
            line = _stripmultispace(line)

        result.append(line)

    return "\n".join(result)


################################################################################
