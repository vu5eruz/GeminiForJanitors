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

PROXY_URL = _env.get("GFJPROXY_EXTERNAL_URL", "")
if not PROXY_URL:
    PROXY_URL = _env.get("RENDER_EXTERNAL_URL", "")
    if not PROXY_URL:
        PROXY_URL = "https://geminiforjanitors.onrender.com"
PROXY_URL = PROXY_URL.rstrip("/")

PROXY_BRANCH = _env.get("GFJPROXY_BRANCH", "")
if not PROXY_BRANCH:
    PROXY_BRANCH = _env.get("RENDER_GIT_BRANCH", "")
    if not PROXY_BRANCH:
        PROXY_BRANCH = "master"
PROXY_BRANCH = PROXY_BRANCH.strip().lower()

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
    int(_env.get("GFJPROXY_PROCESS_TIMEOUT", 120)) - 10,
    60,
)

################################################################################

BANNER_VERSION = 29

BANNER = rf"""***
# **{PROXY_NAME}** ({PROXY_VERSION}){" " + PROXY_BRANCH if PROXY_BRANCH != "master" else ""}
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

### March 30, 2026

● You can now specify a model in /keyring when creating a Gemini CLI key.

### April 7, 2026

● The `//advsettings` command is no more! It's been replaced with five new `//advset_*` commands! See `//help advsettings` for more info.

### April 16, 2026

● The `//prefill` command and its jailbreak have been changed. You can now use `//prefill_mode 0|1|2|3` to select which prefill/jailbreak to use.

● These changes are experimental! Please report any bugs to the Gemini Proxy Guide!
"""

################################################################################
