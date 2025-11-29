from ._globals import DEVELOPMENT, REDIS_URL
from .xuiduser import LocalUserStorage, RedisUserStorage


if REDIS_URL is not None:
    storage = RedisUserStorage(REDIS_URL)
    print(" * Using Redis user storage")
elif DEVELOPMENT:
    storage = LocalUserStorage()
    print(" * WARNING: Using local user storage")
else:
    print(" * ERROR: No user storage")
    exit(1)
