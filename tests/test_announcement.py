import pytest

from gfjproxy._globals import REDIS_URL
from gfjproxy.xuiduser import LocalUserStorage, RedisUserStorage

################################################################################


@pytest.mark.parametrize(
    "storage",
    [
        LocalUserStorage,
        RedisUserStorage,
    ],
)
def test_announcement_basic(storage):
    """Basic functionality test for announcement storage."""

    if storage == RedisUserStorage:
        if not REDIS_URL:
            pytest.skip("No REDIS_URL provided")
        storage = storage(REDIS_URL, timeout=2.5)
    else:
        storage = storage()

    assert storage.active()

    assert storage.announcement == ""

    storage.announcement = "Lorem Ipsum"
    assert storage.announcement == "Lorem Ipsum"

    storage.announcement = ""
    assert storage.announcement == ""
