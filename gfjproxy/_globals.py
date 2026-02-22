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

BANNER_VERSION = 23

BANNER = rf"""***
# {PROXY_NAME} ({PROXY_VERSION})
*Hosted by {PROXY_ADMIN}*

The proxy has had an internal rework, the only notable change being that some errors coming from Google will be displayed as-is, which means the *Resource has been exhausted* error has been replaced by a *This model is currently experiencing high demand* error as reported by Google.

The only regression was incorrect tracking in the proxy's statistics. This should be addressed now.

The URL https://geminiforjanitors-i7zd.onrender.com/ is now listed on gfjproxies!

***

## Commands

You can include one or more commands in your messages, separated by spaces. You can turn on some commands and they will apply across all messages in all chats. Some commands can be called with `this` to make them only apply to the next message. Preset commands need to be called every time you want to use them.

- `//aboutme`
  Shows you info about your proxy usage and what commands you have turned on or off.

- `//banner`
  Shows you this banner, regardless of whether you have seen it before or if you use the `/quiet/` URL.

- `//advsettings on|off|this`
  Enables JanitorAI generation settings: Max Tokens, Top K, Top P, and Frequency/Repetition Penalty. *Note:* use this only if you know what you are doing. *Note:* Top K/P may have no effect.

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

***

## Extras

You can use more than one API key, separated with commas, and the proxy will automatically rotate them for you on every message. You can use this mechanism to streamline the use of multiple Google accounts and amortize requests per day quotas, using only one proxy setting.

You should only see this banner if you are a new user or if there has been a new update. If you don't want to see these banners, change your proxy URL to: `{PROXY_URL}/quiet/`. You are going to miss on updates if you use that URL. You can always use the command `//banner` to receive the latest news regardless of your URL.

***

This proxy is hosted by volunteers, all bound to Render's monthly 100 GB bandwidth quota. Make sure to use different URLs to distribute the load!

Check out `https://gfjproxies.vu5eruz.workers.dev/` for a list of alternative proxies you can use. Choose proxies with low `bandwidth` usage.

Feel free to reroll or edit this message to remove this banner."""

################################################################################
