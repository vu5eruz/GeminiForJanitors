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
def test_annoucement_basic(storage):
    """Basic functionality test for annoucement storage."""

    if storage == RedisUserStorage:
        if not REDIS_URL:
            pytest.skip("No REDIS_URL provided")
        storage = storage(REDIS_URL, timeout=2.5)
    else:
        storage = storage()

    assert storage.active()

    assert storage.annoucement == ""

    storage.annoucement = "Lorem Ipsum"
    assert storage.annoucement == "Lorem Ipsum"

    storage.annoucement = ""
    assert storage.annoucement == ""
