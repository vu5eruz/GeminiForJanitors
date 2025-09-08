import pytest
import secrets

from gfjproxy._globals import REDIS_URL
from gfjproxy.xuiduser import LocalUserStorage, RedisUserStorage, XUID

################################################################################


def test_xuid():
    """Basic object construction and comparison tests."""

    salt_a = secrets.token_bytes(32)
    salt_b = secrets.token_bytes(32)

    user_a = "api-key-a"
    user_b = "api-key-b"

    # same user same salt should be equal
    assert XUID(user_a, salt_a) == XUID(user_a, salt_a)
    assert XUID(user_b, salt_b) == XUID(user_b, salt_b)

    # same user different salt should NOT be equal
    assert XUID(user_a, salt_a) != XUID(user_a, salt_b)
    assert XUID(user_b, salt_a) != XUID(user_b, salt_b)

    # different user same salt should NOT be equal
    assert XUID(user_a, salt_a) != XUID(user_b, salt_a)
    assert XUID(user_a, salt_b) != XUID(user_b, salt_b)

    # different user different salt should NOT be equal
    assert XUID(user_a, salt_a) != XUID(user_b, salt_b)


@pytest.mark.parametrize(
    "other",
    [
        None,
        int(),
        float(),
        complex(),
        bool(),
        list(),
        tuple(),
        range(1),
        str(),
        bytes(),
        bytearray(),
        memoryview(b""),
        set(),
        frozenset(),
        dict(),
    ],
)
def test_xuid_cmp(other):
    """Defensive programming, a XUID must NOT be compared with other types."""

    xuid = XUID("john smith", "The Quick Brown Fox Jumps Over The Lazy Dog")

    with pytest.raises(TypeError):
        _ = xuid == other

    with pytest.raises(TypeError):
        _ = xuid != other


def test_xuid_len():
    """Test whether XUID string lengths are exactly as advertised."""

    xuid = XUID("john smith", "The Quick Brown Fox Jumps Over The Lazy Dog")

    assert len(repr(xuid)) == XUID.LEN_REPR
    assert len(str(xuid)) == XUID.LEN_STR


################################################################################


@pytest.mark.parametrize(
    "storage",
    [
        LocalUserStorage,
        RedisUserStorage,
    ],
)
def test_storage(storage):
    """Basic storage tests."""

    if storage == RedisUserStorage:
        if not REDIS_URL:
            pytest.skip("No REDIS_URL provided")
        storage = storage(REDIS_URL, timeout=2.5)
    else:
        storage = storage()

    assert storage.active()

    salt = secrets.token_bytes(32)

    user_1 = XUID("user-1", salt)
    user_2 = XUID("user-2", salt)
    user_3 = XUID("user-3", salt)
    user_4 = XUID("user-4", salt)

    # Ensure that these users are not in the storage
    assert storage.get(user_1) == ({}, False)
    assert storage.get(user_2) == ({}, False)
    assert storage.get(user_3) == ({}, False)
    assert storage.get(user_4) == ({}, False)

    # Store these users and check that they weren't already in the storage
    assert not storage.put(user_1, {"abc": "def"})
    assert not storage.put(user_2, {"abc": "def"})
    assert not storage.put(user_3, {"abc": "def"})
    assert not storage.put(user_4, {"abc": "def"})

    # Update users' data and check that they are still present in the storage
    assert storage.put(user_1, {"abc": 123})
    assert storage.put(user_2, {"abc": 123})
    assert storage.put(user_3, {"abc": 123})
    assert storage.put(user_4, {"abc": 123})

    # Check that the users are in the storage and their data is stored correctly
    assert storage.get(user_1) == ({"abc": 123}, True)
    assert storage.get(user_2) == ({"abc": 123}, True)
    assert storage.get(user_3) == ({"abc": 123}, True)
    assert storage.get(user_4) == ({"abc": 123}, True)

    # Clean up and check that the storage was cleaned up correctly
    storage.rem(user_1)
    storage.rem(user_2)
    storage.rem(user_3)
    storage.rem(user_4)

    with pytest.raises(KeyError):
        storage.rem(user_1)

    with pytest.raises(KeyError):
        storage.rem(user_2)

    with pytest.raises(KeyError):
        storage.rem(user_3)

    with pytest.raises(KeyError):
        storage.rem(user_4)


################################################################################


@pytest.mark.parametrize(
    "storage",
    [
        LocalUserStorage,
        RedisUserStorage,
    ],
)
def test_locking(storage):
    """Basic storage locking tests."""

    if storage == RedisUserStorage:
        if not REDIS_URL:
            pytest.skip("No REDIS_URL provided")
        storage = storage(REDIS_URL, timeout=2.5)
    else:
        storage = storage()

    assert storage.active()

    salt = secrets.token_bytes(32)

    user_1 = XUID("user-1", salt)
    user_2 = XUID("user-2", salt)

    # Ensure that locking and unlocking allow serial access
    assert storage.lock(user_1)
    storage.unlock(user_1)
    assert storage.lock(user_2)
    storage.unlock(user_2)
    assert storage.lock(user_1)
    storage.unlock(user_1)
    assert storage.lock(user_2)
    storage.unlock(user_2)

    assert storage.lock(user_1)
    storage.unlock(user_1)
    assert storage.lock(user_1)
    storage.unlock(user_1)
    assert storage.lock(user_2)
    storage.unlock(user_2)
    assert storage.lock(user_2)
    storage.unlock(user_2)

    assert storage.lock(user_1)
    assert storage.lock(user_2)
    storage.unlock(user_1)
    storage.unlock(user_2)
    assert storage.lock(user_2)
    assert storage.lock(user_1)
    storage.unlock(user_2)
    storage.unlock(user_1)
    assert storage.lock(user_1)
    assert storage.lock(user_2)
    storage.unlock(user_2)
    storage.unlock(user_1)

    # Ensure that locking and unlocking prevent concurrent access
    assert storage.lock(user_1)
    assert not storage.lock(user_1)
    storage.unlock(user_1)
    assert storage.lock(user_2)
    assert not storage.lock(user_2)
    storage.unlock(user_2)


################################################################################
