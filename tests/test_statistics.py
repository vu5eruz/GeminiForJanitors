import pytest

from gfjproxy.statistics import (
    BUCKET_INTERVAL,
    clear_stats,
    make_stats_bucket,
    make_timestap,
    query_stats,
    track_stats,
)
from gfjproxy.storage import RedisUserStorage, storage

pytestmark = pytest.mark.skipif(
    not isinstance(storage, RedisUserStorage),
    reason="Redis user storage required",
)

################################################################################


def test_statistics_basic():
    """Basic statistics usage."""

    clear_stats(query_stats())

    t0 = make_timestap()
    t1 = t0 + 1 * BUCKET_INTERVAL
    t2 = t0 + 2 * BUCKET_INTERVAL
    t3 = t0 + 3 * BUCKET_INTERVAL
    t4 = t0 + 4 * BUCKET_INTERVAL

    track_stats("r.msg.succeed", timestamp=t0)

    track_stats("r.msg.succeed", timestamp=t1)
    track_stats("r.msg.succeed", timestamp=t1)
    track_stats("r.msg.failed", timestamp=t1)

    track_stats("r.msg.succeed", timestamp=t2)
    track_stats("r.msg.failed", timestamp=t2)
    track_stats("r.msg.succeed", timestamp=t2)
    track_stats("r.msg.failed", timestamp=t2)

    track_stats("r.msg.succeed", timestamp=t3)
    track_stats("r.msg.failed", timestamp=t3)
    track_stats("r.msg.failed", timestamp=t3)

    track_stats("r.msg.failed", timestamp=t4)

    stats = query_stats(t4)

    assert stats == [
        (
            make_stats_bucket(t0),
            {
                "r": 1,
                "r.msg": 1,
                "r.msg.succeed": 1,
            },
        ),
        (
            make_stats_bucket(t1),
            {
                "r": 3,
                "r.msg": 3,
                "r.msg.succeed": 2,
                "r.msg.failed": 1,
            },
        ),
        (
            make_stats_bucket(t2),
            {
                "r": 4,
                "r.msg": 4,
                "r.msg.succeed": 2,
                "r.msg.failed": 2,
            },
        ),
        (
            make_stats_bucket(t3),
            {
                "r": 3,
                "r.msg": 3,
                "r.msg.succeed": 1,
                "r.msg.failed": 2,
            },
        ),
        (
            make_stats_bucket(t4),
            {
                "r": 1,
                "r.msg": 1,
                "r.msg.failed": 1,
            },
        ),
    ]


################################################################################
