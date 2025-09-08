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

PROXY_VERSION = _append_git_version("2025.09.08")

REDIS_URL = _env.get("GFJPROXY_REDIS_URL")

XUID_SECRET = _env.get("GFJPROXY_XUID_SECRET")

################################################################################

BANNER_VERSION = 6

BANNER = rf"""***
# {PROXY_NAME} ({PROXY_VERSION})

Experimental update! Tell your `/quiet/` friends about this!

The proxy will now lock concurrent usage. If you send a message without waiting for another one to finish, you will get an error, regardless of your per minute quotas. This is to reduce load on the proxy, as well as to prevent users from spamming the proxy.

You can now specify more than one API key, separated with commas, and the proxy will automatically rotate them for you on every message. You can use this mechanism to streamline the use of multiple Google accounts and amortize requests per day quotas, using only one proxy setting.

Added the command "`//advsettings on|off`" to enable the use of JanitorAI generation settings, such as Max Tokens, Top K, Top P, and Repetition Penalty. Turn this on to make the proxy use your settings instead of its default values. Use this only if you know what you are doing.

***

Use the commands "`//prefill on`" and "`//prefill off`" to enable or disable Eslezer's prefill. Use "`//prefill this`" to enable the prefill for a single message. This could help prevent STOP or PROHIBITED_CONTENT errors, but that is not guaranteed.

Use the commands "`//think on`", "`//think off`" and "`//think this`" to confuse Gemini into doing it's chain of thought in the response message, potentially bypassing content filters and reducing STOP or PROHIBITED_CONTENT errors. The proxy will attempt to remove any stray <think> or <responses> from the result, but it might fail sometimes.

Use the commands "`//nobot on`", "`//nobot off`" and "`//nobot this`" to remove the entire bot description from the prompt. If all else fails, try it out. THIS WILL NEGATIVELY AFFECT YOUR CHAT UNLESS YOU ALREADY HAVE PLENTY OF MESSAGES WITH THE BOT. The model depends on the bot description to know what to say. Without this, the model will depend exclusively on your chat messages. Make sure to have plenty of messages and a very high Context Size set in your Generation Settings.

***

Use the command "`//preset gigakostyl`" or "`//preset minipopka`" to enhance any sex scenes in the bot's response. You cannot turn a preset on, you have to include this command everytime you want to enhance sex scenes. It is recomended that you use "`//prefill`" or "`//think`" as well.

You cannot use multiple presets at the same time. Only the last one will take effect.

"`//preset minipopka`" will influence the overall writing, mannerisms of characters, and possibly make the bot speak for you.
"`//preset gigakostyl`" is simpler but has a quirk that it adds an "X-RAY" section to scene descriptions.

***

You can use multiple commands in the same message (make sure to separate them with spaces!) for their combined effect.

Use the command "`//aboutme`" (has no effect on the bot) to see what commands you have turned on or off. All these settings are specific to an API key.

***

You should only see this banner if you are a new user or if there has been a new update. If you don't want to see these banners, change your proxy URL to: `https://geminiforjanitors.onrender.com/quiet/`. You are going to miss on updates if you use that URL. You can always use the command `//banner` to receive the latest news regardless of your URL.

Feel free to reroll or edit this message to remove this banner."""

################################################################################
