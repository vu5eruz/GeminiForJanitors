"""Bandwidth management."""

import datetime
import httpx
from ._globals import (
    RENDER_API_KEY,
    RENDER_SERVICE_ID,
)
from .logging import xlog


def bandwidth_usage() -> tuple[int, str | None]:
    xlog(None, "Bandwidth: querying Render ...")

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
        f"Bandwidth: query result: {response.status_code} {response.reason_phrase}",
    )

    if (
        response.status_code == 200
        and isinstance((response_json := response.json()), list)
        and len(response_json) == 1
        and isinstance((usage := response_json[0]), dict)
        and isinstance((unit := usage.get("unit")), str)
        and isinstance((values := usage.get("values")), list)
    ):
        total = sum(float(value.get("value", 0.0)) for value in values)

        xlog(None, f"Bandwidth: query succeeded: {total:.2f} {unit}")

        return (total, unit)

    xlog(None, "Bandwidth: query failed")

    return (-1, None)
