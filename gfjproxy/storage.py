import redis.exceptions

from ._globals import DEVELOPMENT, REDIS_URL
from .xuiduser import LocalUserStorage, RedisUserStorage

if REDIS_URL is not None:
    try:
        storage = RedisUserStorage(REDIS_URL)
        print(" * Using Redis user storage")
    except redis.exceptions.ConnectionError as e:
        print(" * ERROR: Could not connect to Redis")
        print(e)
        exit(1)
elif DEVELOPMENT:
    storage = LocalUserStorage()
    print(" * WARNING: Using local user storage")
else:
    print(" * ERROR: No user storage")
    exit(1)
