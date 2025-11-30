from ._globals import DEVELOPMENT, REDIS_URL
from .xuiduser import LocalUserStorage, RedisUserStorage

if REDIS_URL is not None:
    # Let any exception bubble up
    storage = RedisUserStorage(REDIS_URL)
elif DEVELOPMENT:
    storage = LocalUserStorage()
else:
    storage = None
