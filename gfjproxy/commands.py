"""Commands and processing of messages."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from random import randint

from ._globals import BANNER, BANNER_VERSION, PRESETS
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
    func: Callable | None = field(default=None, repr=False, compare=False, kw_only=True)

    # Prefer to this method instead of directly calling func
    def __call__(self, user, jai_req, response):
        if self.func is None:
            raise RuntimeError(f"Calling {self} without a function pointer")
        return self.func(self.args, user, jai_req, response)


class CommandError(Exception):
    """User error raised by commands."""

    pass


class CommandExit(Exception):
    """Exception to exit processing early raised by commands."""

    pass


COMMANDS = {}


def command(*, argspec: str = "", **kwargs):
    if argspec:
        regex = re.compile(argspec)

    def outer_wrapper(func):
        cmd_name = func.__name__

        @wraps(func)
        def inner_wrapper(args, user, jai_req, response):
            if argspec and not regex.fullmatch(args):  # pyright: ignore[reportPossiblyUnboundVariable]
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
    # U+200B ZERO WIDTH SPACE
    response.add_proxy_message(
        f"Your user ID on this proxy is `{user.xuid!r}`.",
        f"You have used this proxy {user.get_rcounter()} time(s).",
        f"You were {user.last_seen_msg()}.",
        "Your commands are:",
        f"\u200b- //advsettings {'on' if user.use_nobot else 'off'}",
        f"\u200b- //dice_char {'on' if user.use_dice_char else 'off'}",
        f"\u200b- //nobot {'on' if user.use_nobot else 'off'}",
        f"\u200b- //ooctrick {'on' if user.use_ooctrick else 'off'}",
        f"\u200b- //prefill {'on' if user.use_prefill else 'off'}",
        f"\u200b- //search {'on' if user.use_search else 'off'}",
        f"\u200b- //think {'on' if user.use_think else 'off'}",
        f"\u200b- //think_text {user.think_text}",
        f"This message is using API key {jai_req.api_key_index + 1} out of {jai_req.api_key_count}.",
    )
    raise CommandExit()


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


@command(argspec=r"off|on|this", setting="search")
def search(args, user, jai_req, response):
    if jai_req.quiet_commands:
        return response
    return response.add_proxy_message(
        f"Google Search {'enabled' if jai_req.use_search else 'disabled'}"
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


@command(argspec=r"keep|remove")
def think_text(args, user, jai_req, response):
    user.think_text = args
    if jai_req.quiet_commands:
        return response
    return response.add_proxy_message(
        f"Thinking text will be {'kept' if args == 'keep' else 'removed'}."
        + (
            " Make sure to have `//think on` otherwise no thinking will show up."
            if args == "keep"
            else ""
        )
    )


################################################################################


@command(argspec=r"off|on|this", setting="dice_char")
def dice_char(args, user, jai_req, response):
    if jai_req.quiet_commands:
        return response
    return response.add_proxy_message(
        f"Character dice {'enabled' if jai_req.use_dice_char else 'disabled'}"
        + (" (for this message only)." if args == "this" else ".")
    )


@command(argspec=r".+")
def dice_roll(args, user, jai_req, response):
    dice = args.replace("p", "+").replace("m", "-")

    match = re.fullmatch(r"(\d+)?d(\d+)([+-]\d+)?([a-z])?", dice, re.A | re.I)
    if not match:
        return response.add_proxy_message(
            f"Invalid dice syntax `{args}`\nUse the `//dice_help` command for more info."
        )

    count = min(max(int(match.group(1) or "1", base=10), 1), 100)
    faces = max(int(match.group(2), base=10), 2)
    extra = int((match.group(3) or "0"), base=10)

    rolls = [randint(1, faces) for _ in range(count)]
    result = sum(rolls) + extra

    extra_str = f" {'-' if extra < 0 else '+'} {abs(extra)}" if extra != 0 else ""

    result_str = f"{dice} roll: {' + '.join(map(str, rolls))}{extra_str}"
    if extra != 0 or len(rolls) > 1:
        result_str += f" = {result}"
    result_str += "."

    jai_req.append_message(
        "user",
        "\n".join(
            [
                "<system>",
                f"  User {result_str}.",
                "</system>",
            ]
        ),
    )

    return response.add_proxy_message(result_str)


################################################################################


HELP_COMMANDS = """***
You can include one or more commands in your messages, separated by spaces.
You can turn on some commands and they will apply across all messages in all chats.
Some commands can be called with `this` to make them only apply to the next message.
Preset commands need to be called every time you want to use them.

- `//aboutme`
  Shows you info about your proxy usage and what commands you have turned on or off.

- `//banner`
  Shows you the banner, regardless of whether you have seen it before or if you use the `/quiet/` URL.

- `//help commands|dice|multikey|providers`
  Shows you info about specific topics or proxy features.

- `//advsettings on|off|this`
  Enables JanitorAI generation settings: Max Tokens, Top K, Top P, and Frequency/Repetition Penalty. *Note:* use this only if you know what you are doing.

- `//ooctrick on|off|this`
  Inserts two fake OOC messages into the chat when generating, hopefully fooling the content filters and bypassing them.

- `//prefill on|off|this`
  Adds Eslezer's prefill to the chat. This could help prevent errors, but it is not guaranteed.

- `//search on|off|this`
  Enables the use of Google Search, allowing the model to look up any information relevant to the chat.

- `//think on|off|this`
  Tricks Gemini into doing its thinking inside the response to bypass content filters. *Note:* this might cause ᐸthinkᐳ/ᐸresponseᐳ to leak into the bot's messages.

- `//think_text keep|remove`
  Configures the proxy to either include the model's thinking in the response or remove it entirely.

- `//nobot on|off|this`
  Removes the bot's description from the chat, in case it contains ToS-breaking content. *Note:* use this only as a last resort. This will negatively impact your chat.

- `//preset gigakostyl`
  Adds a simple writing guideline for NSFW roleplay, plus "X-ray views" to sex scenes.

- `//preset minipopka`
  Adds a longer writing guideline to enhance narration and NSFW roleplay.

- `//dice_roll [count]d(faces)[(p|m)(extra)]`
- `//dice_char on|off|this`
  Rolls dices using proxy-provided random numbers. See `//help dice` for more info.
"""


HELP_DICE = """***
# **Dice Commands**

Language models can't produce random numbers without bias.
The proxy can provide the model with random numbers, allowing for a more authentic experience.
Use the `//dice_roll` command to roll any dice you specify, let the proxy generate the outcome and let the model interpret it for you.

## **Dice Specification**

To make a `//dice_roll` you first need to describe which kind of dice you want to roll.
Examples: use `//dice_roll d6` to roll one six-faced dice, use `//dice_roll 3d20` to roll three twenty-faced dice.
The syntax is `//dice_roll [count]d(faces)[(p|m)(extra)]`. Stuff inside (parens) is mandatory, stuff inside [brackets] is optional.
You must specify how many `faces` the dice you want to roll has. Any number greater than 1 works. Examples: `d6`, `d20`, `d100`.
You can add a `count` to roll the given dice multiple times. Any number greater than 1 works. Examples: `2d10`, `8d15`.
You can add or substract a fixed amount, the `extra`, to the end result. You must specify whether to add (`p` for "plus") or substract (`m` for "minus"). Any number works. Examples: `d20p5`, `d3m2`.
You can use all these features at the same time. Example: `//dice_roll 5d20p10` means "roll a twenty-faced dice five times and then add 10".

## **The `//dice_roll` and `//dice_char` commands**

When you use the `//dice_roll` command, you and the model get to see the result. This command is for your use.
When you enable the `//dice_char` command, the proxy will roll a dice on every message, hidden from you, in behalf of the character you are role-playing with.
The `//dice_char` command is for passively providing randomness to the environment and the character.
You can use the `//dice_roll` command multiple times in a single message for multiple separate dice rolls. The `//dice_char` command only rolls one dice per message.

## **Summary**

- `//dice_roll [count]d(faces)[(p|m)(extra)]`
  Rolls a dice for you.

- `//dice_char on|off|this`
  Rolls a hidden dice for the character on every message.
"""


HELP_MULTIKEY = """***
# **Multiple API Keys**

You can put multiple API keys, separated by commas, in your proxy settings. \
You can have multiples keys from the same company as well as from different companies.

The proxy switches between them on every request you make \
(chat message, enhance draft, continue reply, auto summarize).

You can use this to get more messages out of keys with limited quotas \
(such as Requests per Day) by distributing your usage across multiple of them.

## **Notes**

There is no limit as to how many keys you can use.

The proxy goes one by one through every key in the same order you put them.

After going through all your keys, the proxy loops to your first key and start over.

Your commands are stored in your first key. \
If you change the first key on your proxy settings, \
then you will have to send your commands again.
"""


HELP_PROVIDERS = """***
# **Model Providers**

This proxy supports different AI companies, called providers, for models and API keys.

The proxy will try to automatically dispatch your requests to \
the appropriate provider, given your models and API keys. \
If that fails, you can always override the proxy's dispatch logic \
by adding the provider at the start of the model name or the API key. \
For example: `google/AQ.Ab8RN...` (Vertex AI API key), `openrouter/z-ai/glm-4.5-air:free` (Z.AI model through OpenRouter).

## **Google AI Studio and Vertex AI** (`google`)

All models that start with `gemini-` will be routed to Google. \
To use Gemma models, you must add `google/` at the start.

All API keys that start with `AIza` will be used with Google models. \
Vertex AI API keys have a different format and you must add `google/` at the start.

## **Cerebras Cloud Inference** (`cerebras`)

To use any Cerebras model, you must add `cerebras/` at the start.

All API keys that start with `csk-` will be used with Cerebras models.

## **OpenRouter** (`openrouter`)

To use any model through OpenRouter, you must add `openrouter/` first and then the full model name.

All API keys that start with `sk-or-v1-` will be used with OpenRouter models.

## **Z.AI** (`z_ai`)

To use any Z.AI model, you must add `z_ai/` at the start.

You must add `z_ai/` at the start of any Z.AI API key.
"""


HELP = {
    "commands": HELP_COMMANDS,
    "dice": HELP_DICE,
    "multikey": HELP_MULTIKEY,
    "providers": HELP_PROVIDERS,
}


@command(argspec=r".+")
def help(args, user, jai_req, response):
    response.add_proxy_message(
        HELP.get(
            args,
            (
                f"There is no help topic `{args}`.\n"
                + "Available topics are: `commands`, `dice`, `multikey`, `providers`."
            ),
        )
    )
    raise CommandExit()


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


def strip_message(raw_message: str) -> str:
    """Clean up the text of a message, meant for model's output."""

    message = _stripproxytext(raw_message.strip("\n")).split("\n")

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
