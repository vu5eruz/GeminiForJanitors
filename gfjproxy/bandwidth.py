"""Bandwidth management."""

import datetime
import httpx
import redis
import threading
from dataclasses import dataclass
from time import perf_counter
from ._globals import PRODUCTION, RENDER_API_KEY, RENDER_SERVICE_ID
from .logging import xlog
from .start_time import START_TIME
from .storage import storage
from .xuiduser import RedisUserStorage


@dataclass(frozen=True, kw_only=True)
class BandwidthUsage:
    total: int = -1  # MiB

    def __bool__(self):
        return self.total >= 0


def query_bandwidth_usage() -> BandwidthUsage:
    if not PRODUCTION:
        total = perf_counter() - START_TIME
        xlog(None, f"Bandwidth: using mock total {total:.2f} MiB")
        return BandwidthUsage(total=int(total))

    xlog(None, "Bandwidth: querying ...")

    end_time = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    start_time = end_time.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    response = httpx.get(
        "https://api.render.com/v1/metrics/bandwidth",
        params={
            "resource": RENDER_SERVICE_ID,
            "endTime": end_time.isoformat() + "Z",
            "startTime": start_time.isoformat() + "Z",
        },
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {RENDER_API_KEY}",
        },
    )

    xlog(
        None,
        f"Bandwidth: {response.status_code} {response.reason_phrase}",
    )

    if (
        response.status_code == 200
        and isinstance((response_json := response.json()), list)
        and len(response_json) == 1
        and isinstance((usage := response_json[0]), dict)
        and usage.get("unit") == "mb"  # Render seems to always returns MiB
        and isinstance((values := usage.get("values")), list)
    ):
        total = sum(float(value.get("value", 0.0)) for value in values)

        xlog(None, f"Bandwidth: query succeeded: {total:.2f} MiB")

        return BandwidthUsage(total=int(total))

    xlog(None, "Bandwidth: query failed")

    return BandwidthUsage()


def update_bandwidth_usage(lock: redis.lock.Lock) -> None:
    if result := query_bandwidth_usage():
        # Only update the cache if the query is successful, i.e result is positive
        storage._client.set(":bandwidth-cache", str(result.total))
        storage._client.set(":bandwidth-cache-fresh", "<3", ex=60)

    try:
        lock.release()
    except redis.exceptions.LockNotOwnedError:
        pass


def bandwidth_usage() -> BandwidthUsage:
    # Redis storage is always required while an Render API is only required on production
    if not isinstance(storage, RedisUserStorage) or (PRODUCTION and not RENDER_API_KEY):
        return BandwidthUsage()

    if not storage._client.get(":bandwidth-cache-fresh"):
        lock = storage._client.lock(
            name=":bandwidth-cache-lock",
            timeout=30,
            thread_local=False,
        )
        if lock.acquire(blocking=False):
            threading.Thread(
                target=update_bandwidth_usage,
                args=(lock,),
                daemon=True,
            ).start()

    if cache := storage._client.get(":bandwidth-cache"):
        return BandwidthUsage(total=int(cache))
    return BandwidthUsage()
