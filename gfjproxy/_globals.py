"""Proxy global variables."""

from os import environ as _env


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
    "gemini-2.5-flash-lite-preview-06-17",
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-pro",
    "gemini-2.5-pro-preview-03-25",
    "gemini-2.5-pro-preview-05-06",
    "gemini-2.5-pro-preview-06-05",
]

PREFILL = "prefill.txt"

PROXY_AUTHORS = [
    "@undefinedundefined (vu5eruz on GitHub)",
]

PROXY_NAME = "GeminiForJanitors"

PROXY_VERSION = _append_git_version("2025.08.04")

REDIS_URL = _env.get("GFJPROXY_REDIS_URL")

XUID_SECRET = _env.get("GFJPROXY_XUID_SECRET")

################################################################################

BANNER = rf"""***
# {PROXY_NAME} ({PROXY_VERSION})

The proxy has had a major internal rewrite and development should now be smoother. Tell your `/quiet/` friends about this!

Use the commands "`//prefill on`" and "`//prefill off`" to enable or disable Eslezer's prefill. Use "`//prefill this`" to enable the prefill for a single message. This could help prevent PROHIBITED_CONTENT errors, but that is not guaranteed.

Likewise, you can use the commands "`//squash on`", "`//squash off`" and "`//squash this`" to apply NoAss Extension's message squashing before sending your chat to the model. This too could help prevent PROHIBITED_CONTENT errors, not guaranteed, but it could also introduce artifacts into your chat messages.

Use the commands "`//nobot on`", "`//nobot off`" and "`//nobot this`" to remove the entire bot description from the prompt. If all else fails, try it out. THIS WILL NEGATIVELY AFFECT YOUR CHAT UNLESS YOU ALREADY HAVE PLENTY OF MESSAGES WITH THE BOT. The model depends on the bot description to know what to say. Without this, the model will depend exclusively on your chat messages. Make sure to have plenty of messages and a very high Context Size set in your Generation Settings.

You can use multiple commands in the same message (make sure to separate them with spaces!) for their combined effect.

***

You should only see this banner if you are a new user or if there has been a new update. If you don't want to see these banners, change your proxy URL to: `https://geminiforjanitors.onrender.com/quiet/`. You are going to miss on updates if you use this URL. You can always use the command `//banner` to receive the latest news regardless of your URL.

Feel free to reroll or edit this message to remove this banner."""

BANNER_VERSION = 1

################################################################################
