"""Proxy global variables."""

import subprocess
from datetime import UTC, datetime, timedelta
from os import environ as _env
from os import scandir as _scandir
from os.path import dirname as _dirname

################################################################################


CWD = _dirname(__file__)


def _fallback_env(*names) -> str | None:
    for name in names:
        # Check that the environment variable is not None and not the empty string
        if value := _env.get(name):
            return value
    return None


def _get_proxy_branch() -> str:
    branch = (
        _fallback_env(
            "GFJPROXY_BRANCH",
            "RAILWAY_GIT_BRANCH",
            "RENDER_GIT_BRANCH",
        )
        or "unknown"
    )

    try:
        res = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            cwd=CWD,
            text=True,
            check=True,
        )
        if resstr := res.stdout.strip():
            branch = resstr
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    return branch


def _get_proxy_version() -> str:
    version = (
        _fallback_env(
            "GFJPROXY_VERSION",
            "RAILWAY_GIT_COMMIT_SHA",
            "RENDER_GIT_COMMIT",
        )
        or "unknown"
    )

    try:
        res = subprocess.run(
            ["git", "log", "-1", "--format=%ct-%h"],
            capture_output=True,
            cwd=CWD,
            text=True,
            check=True,
        )
        if resstr := res.stdout.strip():
            timestamp, commit = resstr.split("-", maxsplit=1)

            # The previous code used "--date=format:%Y.%m.%d --format=%ad-%h" to format
            # the version string, leading to it being implicitly dependent on the timezone
            # of the committer. Since up to the time of writing, the only author has been
            # from the UTC-4 timezone, it is possible to maintain backwards compat with old
            # deployments by making the versioning scheme officially based on UTC-4 and
            # independent of the committer's timezone. This makes it possible to always
            # reliably derive a version from a commit hash and its UTC timestamp alone, such
            # as those provided from the GitHub APIs.

            dt = datetime.fromtimestamp(int(timestamp), tz=UTC) - timedelta(hours=4)

            version = f"{dt:%Y.%m.%d}-{commit}"
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

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

PROXY_BRANCH = _get_proxy_branch()

PROXY_VERSION = _get_proxy_version()

PROXY_URL = (
    _fallback_env(
        "GFJPROXY_EXTERNAL_URL",
        "RAILWAY_PUBLIC_DOMAIN",
        "RENDER_EXTERNAL_URL",
    )
    or "https://geminiforjanitors.onrender.com"
).rstrip("/")

COOLDOWN = _env.get("GFJPROXY_COOLDOWN", "0")

BANDWIDTH_WARNING = int(
    _env.get("GFJPROXY_BANDWIDTH_WARNING", "76800")
)  # 75 GiB in MiB

RENDER_API_KEY = _env.get("GFJPROXY_RENDER_API_KEY")

RENDER_SERVICE_ID = _env.get("RENDER_SERVICE_ID")

REDIS_URL = _env.get("GFJPROXY_REDIS_URL")

XUID_SECRET = _env.get("GFJPROXY_XUID_SECRET")

STATS_DURATION = int(_env.get("GFJPROXY_STATS_DURATION", "24"))

################################################################################

# Changing this has an impact on whether the runner (specifically gunicorn) will
# forcefully reset a worker after taking too long to answer a request. When
# deploying using gunicorn, make sure to provide a -t value larger than the one
# in here, to prevent issues from arising at run-time.
PROCESS_TIMEOUT: int = max(
    int(_env.get("GFJPROXY_PROCESS_TIMEOUT", "300")) - 10,
    60,
)

################################################################################

BANNER_VERSION = 35

BANNER = rf"""***
# **{PROXY_NAME}** ({PROXY_VERSION} {PROXY_BRANCH})
*Hosted by {PROXY_ADMIN}*

This proxy is hosted by volunteers, bound to Render's monthly 100 GB bandwidth quota.
Go to `https://gfjproxies.vu5eruz.workers.dev/` for a list of URLs you can use.
Make sure to use URLs with low `bandwidth` usage!

***

## **Features**

You can use commands and set jailbreaks in your chat. Send a message with `//help commands` for more info.

You can use multiple API keys and automatically switch between them. Send a message with `//help multikey` for more info.

You can use models from different companies: Cerebras, DeepSeek, Google, Nvidia NIM, OpenRouter, and Z.AI. Send a message with `//help providers` for more info.

You can see proxy statistics and find out if there are more errors than usual. Open `{PROXY_URL}/stats` to find out.

You should only see this banner if you are a new user or if there is an update. Send a message with `//banner` to see this banner again. Change your proxy URL to `{PROXY_URL}/quiet/` to disable it.

***

## **Notice**

On **August 1, 2026**, Render will impose a 5 GB bandwidth limit on free instances, which will suspend all public URLs very quickly.
Anyone with knowledge in Python programming can help porting and deploying the proxy to other clouds, such as Netlify, Vercel, or Railway.
Pull requests are welcome at `https://github.com/vu5eruz/GeminiForJanitors` for contributions.

***

## **Updates**

## June 19, 2026

● Notice: if you are using API keys that start with `AIza`, know that Google will reject them starting September 2026! You are advised to update all your keys to the new `AQ.` type!  See https://ai.google.dev/gemini-api/docs/api-key for more info.

## July 28, 2026

● The proxy has had an internal rework and the Gemini provider code was changed. Please report any issues to the Gemini Proxy Guide.

● New command `//fixturns` is now available to help deal with "`requests ending with a model turn are not supported`" errors!

"""

################################################################################
