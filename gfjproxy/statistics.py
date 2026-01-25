"""Proxy Statistics"""

from collections import defaultdict
from time import gmtime, strftime, time

from .storage import get_redis_client

BUCKET_COUNT = 48  # Number of buckets to keep in storage
BUCKET_INTERVAL = 30 * 60  # Half an hour in seconds
BUCKET_LIFESPAN = 25 * 60 * 60  # Bucket expiry in seconds (25 hours)


type Statistics = list[tuple[str, dict[str, int]]]


def make_stats_bucket(timestamp: float) -> str:
    return strftime(":stats:%Y-%m-%dT%H:%M", gmtime(timestamp))


def make_timestamp() -> float:
    return float(int(time() // BUCKET_INTERVAL) * BUCKET_INTERVAL)


def track_stats(full_key: str, timestamp: float | None = None):
    client = get_redis_client()
    if not client:
        return

    if timestamp is None:
        timestamp = make_timestamp()

    bucket = make_stats_bucket(timestamp)
    sub_keys = full_key.split(".")

    pipeline = client.pipeline()
    for i in range(1, len(sub_keys) + 1):
        key = ".".join(sub_keys[:i])
        pipeline.hincrby(bucket, key, 1)
    pipeline.expire(bucket, BUCKET_LIFESPAN)
    pipeline.execute()


def query_stats(timestamp: float | None = None) -> Statistics:
    client = get_redis_client()
    if not client:
        return []

    if timestamp is None:
        timestamp = make_timestamp()

    buckets = [
        make_stats_bucket(timestamp - delta * BUCKET_INTERVAL)
        for delta in range(0, BUCKET_COUNT)
    ]

    pipeline = client.pipeline()
    for key in buckets:
        pipeline.hgetall(key)
    statistics = pipeline.execute()

    result: Statistics = []

    for bucket, stats in zip(buckets, statistics):
        if not stats:
            continue

        dd = defaultdict(int)
        for key, value in stats.items():
            dd[key.decode()] = int(value.decode())

        result.append((bucket, dd))

    result.reverse()

    return result


def clear_stats(statistics: Statistics):
    """For testing only: ensure that stats data don't persist across tests."""

    client = get_redis_client()
    if not client:
        return

    pipeline = client.pipeline()
    for bucket, stats in statistics:
        for key in stats.keys():
            pipeline.hdel(bucket, key)
    pipeline.execute()
