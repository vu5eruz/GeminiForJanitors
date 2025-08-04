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

PREFILL = "prefill.txt"

PROXY_AUTHORS = [
    "@undefinedundefined (vu5eruz on GitHub)",
]

PROXY_NAME = "GeminiForJanitors"

PROXY_VERSION = _append_git_version("2025.08.04")

REDIS_URL = _env.get("GFJPROXY_REDIS_URL")

XUID_SECRET = os.environ.get("XUID_SECRET")

################################################################################

BANNER = rf"""***
# {PROXY_NAME} ({PROXY_VERSION})

Proxy had a major internal rewrite, development should be smoother. The database has been reset.

You should only see this banner if you are a new user or there's been a new update.
If you don't want to see these banners, change your proxy URL to: https://geminiforjanitors.onrender.com/quiet/
You can always use the command //banner to receive the latest news.

Feel free to reroll or edit this message to remove this banner."""

BANNER_VERSION = 1

################################################################################
