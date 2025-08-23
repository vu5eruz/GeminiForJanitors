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
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-pro",
    "gemini-2.5-pro-preview-03-25",
    "gemini-2.5-pro-preview-05-06",
    "gemini-2.5-pro-preview-06-05",
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

PROXY_VERSION = _append_git_version("2025.08.23")

REDIS_URL = _env.get("GFJPROXY_REDIS_URL")

XUID_SECRET = _env.get("GFJPROXY_XUID_SECRET")

################################################################################

BANNER = rf"""***
# {PROXY_NAME} ({PROXY_VERSION})

Major update! Tell your `/quiet/` friends about this!

**Added "`//think`" command to to help prevent rejections. If you are getting too many STOP or PROHIBITED_CONTENT errors, try this out!**

Added "`//preset minipopka`" as an alternative to `gigakostyl`.

***

Use the commands "`//prefill on`" and "`//prefill off`" to enable or disable Eslezer's prefill. Use "`//prefill this`" to enable the prefill for a single message. This could help prevent STOP or PROHIBITED_CONTENT errors, but that is not guaranteed.

Use the commands "`//think on`", "`//think off`" and "`//think this`" to confuse Gemini into doing it's chain of thought in the response message, potentially bypassing content filters and reducing STOP or PROHIBITED_CONTENT errors. The proxy will attempt to remove any stray <think> or <responses> from the result, but it might fail sometimes.

Use the commands "`//nobot on`", "`//nobot off`" and "`//nobot this`" to remove the entire bot description from the prompt. If all else fails, try it out. THIS WILL NEGATIVELY AFFECT YOUR CHAT UNLESS YOU ALREADY HAVE PLENTY OF MESSAGES WITH THE BOT. The model depends on the bot description to know what to say. Without this, the model will depend exclusively on your chat messages. Make sure to have plenty of messages and a very high Context Size set in your Generation Settings.

***

Use the command "`//preset gigakostyl`" or "`//preset minipopka`" to enhance any sex scenes in the bot's response. You cannot turn a preset on, you have to include this command everytime you want to enhance sex scenes. It is recomended that you use "`//prefill`" or "`//think`" as well.

You cannot use multiple presets at the same time. Only the last one will take effect.

"`//preset minipopka`" can influence the overall writing of a scene and the mannerisms of characters.
"`//preset gigakostyl`" is simpler but has a quirk that it adds an "X-RAY" section to scene descriptions.

***

You can use multiple commands in the same message (make sure to separate them with spaces!) for their combined effect.

Use the command "`//aboutme`" (has no effect on the chat) to see what commands you have turned on or off. All these settings are specific to an API key.

***

You should only see this banner if you are a new user or if there has been a new update. If you don't want to see these banners, change your proxy URL to: `https://geminiforjanitors.onrender.com/quiet/`. You are going to miss on updates if you use that URL. You can always use the command `//banner` to receive the latest news regardless of your URL.

Feel free to reroll or edit this message to remove this banner."""

BANNER_VERSION = 4

################################################################################
