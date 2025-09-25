"""Proxy global variables."""

from os import environ as _env
from os import scandir as _scandir


# Based on https://github.com/numpy/numpy/blob/c6169853b871411ef207db1987a27f134a89b1cb/numpy/_build_utils/gitversion.py#L21
def _append_git_version(version):
    import os.path
    import subprocess

    try:
        p = subprocess.Popen(
            ["git", "log", "-1", "--format=%H"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(__file__),
        )
    except FileNotFoundError:
        pass
    else:
        out, err = p.communicate()

        if p.returncode == 0:
            git_hash = out.decode("utf-8").strip()

            if git_hash:
                version += f"-{git_hash[:7]}"

    return version


################################################################################

if _env.get("GFJPROXY_DEVELOPMENT"):
    DEVELOPMENT = True
    PRODUCTION = False
else:
    DEVELOPMENT = False
    PRODUCTION = True

################################################################################

CLOUDFLARED = _env.get("GFJPROXY_CLOUDFLARED")

# XXX: Manually keep this up to date
MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-lite-preview-06-17",
    "gemini-2.5-flash-lite-preview-09-2025",
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-flash-preview-09-2025",
    "gemini-2.5-pro",
    "gemini-2.5-pro-preview-03-25",
    "gemini-2.5-pro-preview-05-06",
    "gemini-2.5-pro-preview-06-05",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-pro-latest",
]

# XXX: FileNotFoundError
with open("prefill.txt", encoding="utf-8") as prefill:
    PREFILL = prefill.read()
with open("think.txt", encoding="utf-8") as think:
    THINK = think.read()

PRESETS = {}
for entry in _scandir("presets"):
    if entry.is_file():
        with open(f"presets/{entry.name}", encoding="utf-8") as preset:
            PRESETS[entry.name.split(".")[0]] = preset.read()


PROXY_AUTHORS = [
    "@undefinedundefined (vu5eruz on GitHub)",
]

PROXY_NAME = "GeminiForJanitors"

PROXY_VERSION = _append_git_version("2025.09.25")

REDIS_URL = _env.get("GFJPROXY_REDIS_URL")

XUID_SECRET = _env.get("GFJPROXY_XUID_SECRET")

################################################################################

BANNER_VERSION = 8

BANNER = rf"""***
# {PROXY_NAME} ({PROXY_VERSION})

Minor update.

It seems JanitorAI doesn't send **Top K**, **Top P** settings to proxies, meaning that //advsettings only works with **Max Tokens**, and **Frequency/Repetition Penalty**.

**Response Prefill** and **Forbidden Words and Phrases** don't require //advsettings to work.

Support for the following models have been added:
- `gemini-2.5-flash-lite-preview-09-2025`
- `gemini-2.5-flash-preview-09-2025`
- `gemini-flash-latest`
- `gemini-flash-lite-latest`
- `gemini-pro-latest`

The proxy is still locked out from new and infrequent users until Oct 1st. That hasn't changed.

***

## Commands

You can include one or more commands in your messages, separated by spaces. You turn on some commands and they will apply across all messages in all chats. Some commands can be called with `this` to make them only apply to the next message. Preset commands need to be called every time you want to use them.

- `//aboutme`

  Shows you info about your proxy usage and what commands you have turned on or off.

- `//banner`

  Shows you this banner, regardless of whether you have seen it before or if you use the `/quiet/` URL.

- `//advsettings on|off|this`

  Enables JanitorAI generation settings: Max Tokens, Top K, Top P, and Frequency/Repetition Penalty. *Note:* use this only if you know what you are doing.

- `//prefill on|off|this`

  Adds Eslezer's prefill to the chat. This could help prevent errors, but it is not guaranteed.

- `//think on|off|this`

  Tricks Gemini into doing its thinking inside the response to bypass content filters. *Note:* this might cause <think>/<response> to leak into messages.

- `//nobot on|off|this`

  Removes the bot's description from the chat, in case it contains ToS-breaking content. *Note:* use this only as a last resort. This will negatively impact your chat.

- `//preset gigakostyl`

  Adds a simple writing guideline for NSFW roleplay, plus "X-ray views" to sex scenes.

- `//preset minipopka`
  Adds a longer writing guideline to enhance narration and NSFW roleplay.

***

## Extras

You can use more than one API key, separated with commas, and the proxy will automatically rotate them for you on every message. You can use this mechanism to streamline the use of multiple Google accounts and amortize requests per day quotas, using only one proxy setting.

You should only see this banner if you are a new user or if there has been a new update. If you don't want to see these banners, change your proxy URL to: `https://geminiforjanitors.onrender.com/quiet/`. You are going to miss on updates if you use that URL. You can always use the command `//banner` to receive the latest news regardless of your URL.

Feel free to reroll or edit this message to remove this banner."""

################################################################################
