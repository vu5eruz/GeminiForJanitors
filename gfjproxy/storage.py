from redis import Redis

from ._globals import REDIS_URL
from .xuiduser import LocalUserStorage, RedisUserStorage

if REDIS_URL is not None:
    # Let any exception bubble up
    storage = RedisUserStorage(REDIS_URL)
else:
    storage = LocalUserStorage()


def get_redis_client() -> Redis | None:
    if isinstance(storage, RedisUserStorage):
        return storage._client
    return None
