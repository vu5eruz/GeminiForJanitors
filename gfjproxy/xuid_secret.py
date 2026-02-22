from secrets import token_bytes

from ._globals import XUID_SECRET

if XUID_SECRET is not None:
    xuid_secret = XUID_SECRET.encode("utf-8")
else:
    xuid_secret = token_bytes(32)
