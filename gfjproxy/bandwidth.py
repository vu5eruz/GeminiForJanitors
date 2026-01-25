"""Bandwidth management."""

import datetime
import threading
from dataclasses import dataclass
from time import perf_counter

import redis
import redis.exceptions
import redis.lock

from ._globals import BANDWIDTH_WARNING, PRODUCTION, RENDER_API_KEY, RENDER_SERVICE_ID
from .http_client import http_client
from .logging import xlog
from .start_time import START_TIME
from .storage import get_redis_client, storage


@dataclass(frozen=True, kw_only=True)
class BandwidthUsage:
    total: int = -1
    "Total bandwidth usage in MiB."

    def __bool__(self):
        return self.total >= 0


def _query_bandwidth_usage() -> BandwidthUsage:
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
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

    response = http_client.get(
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


def _update_bandwidth_usage(client: redis.Redis, lock: redis.lock.Lock) -> None:
    if result := _query_bandwidth_usage():
        # Only update the cache if the query is successful, i.e result is positive
        client.set(":bandwidth-cache", result.total)
        client.set(":bandwidth-cache-fresh", "<3", ex=300)  # 5 minutes

        if 0 < BANDWIDTH_WARNING <= result.total:
            xlog(None, "Bandwidth: announcement set")
            storage.announcement = "\n".join(
                (
                    f"Bandwidth quota is above {BANDWIDTH_WARNING / 1024:.1f} GiB.",
                    "Please consider using another URL.",
                )
            )
        else:
            xlog(None, "Bandwidth: announcement clear")
            storage.announcement = ""

    try:
        lock.release()
    except redis.exceptions.LockNotOwnedError:
        pass


def bandwidth_usage() -> BandwidthUsage:
    client = get_redis_client()

    # Redis storage is always required while an Render API is only required on production
    if client is None or (PRODUCTION and not RENDER_API_KEY):
        return BandwidthUsage()

    if not client.get(":bandwidth-cache-fresh"):
        lock = client.lock(
            name=":bandwidth-cache-lock",
            timeout=30,
            thread_local=False,
        )
        if lock.acquire(blocking=False):
            threading.Thread(
                target=_update_bandwidth_usage,
                args=(client, lock),
                daemon=True,
            ).start()

    if isinstance((cache := client.get(":bandwidth-cache")), bytes):
        return BandwidthUsage(total=int(cache))
    return BandwidthUsage()
