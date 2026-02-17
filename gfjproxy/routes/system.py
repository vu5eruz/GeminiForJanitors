from time import perf_counter

from flask import Blueprint, redirect, render_template, request, send_from_directory

from .._globals import (
    BANDWIDTH_WARNING,
    PROXY_ADMIN,
    PROXY_NAME,
    PROXY_URL,
    PROXY_VERSION,
)
from ..bandwidth import bandwidth_usage
from ..cooldown import cooldown_policy, get_cooldown
from ..logging import xlog
from ..start_time import START_TIME
from ..statistics import make_timestamp, query_stats
from ..storage import get_redis_client, storage

system = Blueprint("system", __name__)


@system.route("/", methods=["GET"])
@system.route("/index", methods=["GET"])
@system.route("/index.html", methods=["GET"])
def index():
    assert storage is not None  # Make type checkers happy

    if request.path != "/":
        return redirect("/", code=301)

    xlog(None, "Handling index")

    return render_template(
        "index.html",
        admin=PROXY_ADMIN,
        announcement=storage.announcement,
        title=PROXY_NAME,
        version=PROXY_VERSION,
    )


@system.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.ico")


@system.route("/health")
@system.route("/healthz")
def health():
    keyspace = -1
    if client := get_redis_client():
        if keyspace_info := client.info("keyspace"):
            assert isinstance(keyspace_info, dict)
            keyspace = int(keyspace_info.get("db0", {}).get("keys", -1))

    usage = bandwidth_usage()

    health = {
        "admin": PROXY_ADMIN,
        "bandwidth": usage.total,
        "bwarning": BANDWIDTH_WARNING,
        "cooldown": get_cooldown(usage),
        "cpolicy": str(cooldown_policy),
        "keyspace": keyspace,
        "uptime": int(perf_counter() - START_TIME),
        "version": PROXY_VERSION,
    }

    if request.headers.get("accept", "").split(",")[0] == "text/html":
        return render_template(
            "health.html",
            health=health,
            title=f"Health - {PROXY_NAME}",
            url=PROXY_URL,
        )

    # Return health data as JSON
    return health, 200


@system.route("/stats")
def stats():
    xlog(None, "Handling stats")

    timestamp = make_timestamp()
    statistics = query_stats(timestamp)

    statistics_json = {}
    for bucket, stats in statistics:
        statistics_json[bucket] = dict(stats)

    if request.headers.get("accept", "").split(",")[0] == "text/html":
        latest_stats = {}
        stats_begin = "N/A"
        stats_end = "N/A"

        if statistics:
            latest_stats = statistics[-1][1]
            stats_begin = statistics[0][0].removeprefix(":stats:")
            stats_end = statistics[-1][0].removeprefix(":stats:")

        return render_template(
            "stats.html",
            title=f"Statistics - {PROXY_NAME}",
            url=PROXY_URL,
            statistics=statistics_json,
            stats_begin=stats_begin.replace("T", " "),
            stats_end=stats_end.replace("T", " "),
            latest_stats=latest_stats,
        )

    # Return statistics data as JSON
    return statistics_json, 200
