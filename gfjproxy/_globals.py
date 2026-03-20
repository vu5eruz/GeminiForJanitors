"""Proxy global variables."""

from datetime import datetime, timedelta, timezone
from os import environ as _env
from os import scandir as _scandir


def _make_git_version():
    import os.path
    import subprocess

    version = "unknown"

    try:
        p = subprocess.Popen(
            ["git", "log", "-1", "--format=%ct-%h"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(__file__),
        )
    except Exception:
        pass
    else:
        out, _ = p.communicate()

        if p.returncode == 0 and out:
            timestamp_hash = out.decode().strip().split("-", maxsplit=2)
            if len(timestamp_hash) == 2:
                timestamp, hash = timestamp_hash

                # The previous code used "--date=format:%Y.%m.%d --format=%ad-%h" to format
                # the version string, leading to it being implicitly dependent on the timezone
                # of the committer. Since up to the time of writting, the only author has been
                # from the UTC-4 timezone, it is possible to maintain backwards compat with old
                # deployments by making the versioning scheme officially based on UTC-4 and
                # independent of the committer's timezone. This makes it possible to always
                # reliably derive a version from a commit hash and its UTC timestamp alone, such
                # as those provided from the GitHub APIs.

                dt = datetime.fromtimestamp(
                    int(timestamp), tz=timezone.utc
                ) - timedelta(hours=4)

                version = f"{dt:%Y.%m.%d}-{hash}"

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
    "@undefinedundefined (@undefined_anon on Discord, vu5eruz on GitHub)",
]

PROXY_ADMIN = _env.get("GFJPROXY_ADMIN", "Anonymous")

PROXY_NAME = "GeminiForJanitors"

PROXY_VERSION = _make_git_version()

PROXY_URL = _env.get("GFJPROXY_EXTERNAL_URL", "").rstrip("/")
if not PROXY_URL:
    PROXY_URL = _env.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not PROXY_URL:
        PROXY_URL = "https://geminiforjanitors.onrender.com"

COOLDOWN = _env.get("GFJPROXY_COOLDOWN", "0")

BANDWIDTH_WARNING = int(_env.get("GFJPROXY_BANDWIDTH_WARNING", 76800))  # 75 GiB in MiB

if (_RENDER_API_KEY := _env.get("GFJPROXY_RENDER_API_KEY", "")).startswith("rnd_"):
    RENDER_API_KEY = _RENDER_API_KEY
else:
    RENDER_API_KEY = None

RENDER_SERVICE_ID = _env.get("RENDER_SERVICE_ID")

REDIS_URL = _env.get("GFJPROXY_REDIS_URL")

XUID_SECRET = _env.get("GFJPROXY_XUID_SECRET")

STATS_DURATION = int(_env.get("GFJPROXY_STATS_DURATION", 24))

################################################################################

# Changing this has an impact on whether the runner (specifically gunicorn) will
# forcefully reset a worker after taking too long to answer a request. When
# deploying using gunicorn, make sure to provide a -t value larger than the one
# in here, to prevent issues from arising at run-time.
PROCESS_TIMEOUT: int = max(
    int(_env.get("GFJPROXY_PROCESS_TIMEOUT", 90)) - 15,
    60,
)

################################################################################

BANNER_VERSION = 27

BANNER = rf"""***
# **{PROXY_NAME}** ({PROXY_VERSION})
*Hosted by {PROXY_ADMIN}*

This proxy is hosted by volunteers, bound to Render's monthly 100 GB bandwidth quota.
Go to `https://gfjproxies.vu5eruz.workers.dev/` for a list of URLs you can use.
Make sure to use URLs with low `bandwidth` usage!

***

## **Features**

You can use commands and set jailbreaks in your chat. Send a message with `//help commands` for more info.

You can use multiple API keys and automatically switch between them. Send a message with `//help multikey` for more info.

You can use models from different companies: Cerebras, Google, OpenRouter and Z.AI. Send a message with `//help providers` for more info.

You can see proxy statistics and find out if there are more errors than usual. Open `{PROXY_URL}/stats` to find out.

You should only see this banner if you are a new user or if there is an update. Send a message with `//banner` to see this banner again. Change your proxy URL to `{PROXY_URL}/quiet/` to disable it.

***

## **Updates**

### March 16, 2026

● Added support for different providers! You can now use models from other companies!

● Added support for **Cerebras**! Its API keys start with `csk-` and to use a model you need to add `cerebras/` at the start: `cerebras/llama3.1-8b`

● Added support for **Z.AI**! You must add `z_ai/` at the start of its API keys and to use a model you need to add `z_ai/` at the start: `z_ai/glm-4.7-flash`

● Added support for **Gemini CLI**! Its API keys start with `gfjproxy.gemini_cli.` and to use a model you need to add `gemini_cli/` at the start: `gemini_cli/gemini-3-pro-preview`

### March 17, 2026

● The banner was been rewritten! Hopefully you will all find it easier to read.

● Added support for **OpenRouter**! Its API keys start with `sk-or-v1-` and to use a model you need to write it in full: `openrouter/stepfun/step-3.5-flash:free`

### March 20, 2026

● Fixed a bug that caused Internal Proxy Error while serving OpenRouter requests. It should work now.
"""

################################################################################
