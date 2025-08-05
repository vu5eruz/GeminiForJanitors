"""X-Unique/User Identifier (XUID) and User Settings/Storage.

XUIDs are a mechanism to anonymously identify unique users from sensitive data.
The proxy has no access to any user-unique data or info except their API keys.
Hashing an API key with a secret salt gives an unique user ID for program use.
"""

import json
import redis
from base64 import urlsafe_b64encode as _base64
from colorama.ansi import Fore as _colorama_ansi_fore
from hashlib import sha256 as _hash_fun  # Choice of hash function is arbitrary
from hmac import digest as _hmac_digest
from time import time as _unix_time

_color_palette = [
    # no black, it'd be unreadable on dark theme
    _colorama_ansi_fore.RED,
    _colorama_ansi_fore.GREEN,
    _colorama_ansi_fore.YELLOW,
    _colorama_ansi_fore.BLUE,
    _colorama_ansi_fore.MAGENTA,
    _colorama_ansi_fore.CYAN,
    # no white, it'd be unreadable on light theme
]

_color_reset = _colorama_ansi_fore.RESET

################################################################################


class XUID:
    """X-Unique/User Identifier.

    :param user: The user's API key or any sensitive unique identifier.
    :param salt: Program global secure random string.

    Usage::

      >>> import secrets
      >>> import xuiduser
      >>> XUID_SALT = secrets.token_bytes(32) # or os.environ["XUID_SALT"]
      >>> user_api_key = "..." # provided to the proxy during a request
      >>> xuid = xuiduser.XUID(user_api_key, XUID_SALT)

    Notes::

      Comparing XUIDs with other types causes an exception, which can lead to
      issues should a XUID be part of any collections with heterogeneous types.
      This is the intended behavior. XUIDs must be handled with utmost care."""

    LEN_REPR = (4 * _hash_fun().digest_size + 2) // 3
    LEN_STR = 8  # Arbitrary, could be made a global proxy settings
    LEN_PRETTY = LEN_STR + 2  # Does not includes non-visible ANSI escape codes

    def __init__(self, user: str | bytes, salt: str | bytes):
        user = user.encode("utf-8") if isinstance(user, str) else user
        salt = salt.encode("utf-8") if isinstance(salt, str) else salt

        self._xuid_raw = _hmac_digest(salt, user, _hash_fun)
        self._xuid_str = _base64(self._xuid_raw).rstrip(b"=").decode("ascii")

    def __hash__(self) -> int:
        return hash(self._xuid_raw)

    def __repr__(self) -> str:
        """Returns the full XUID value representation as a string.
        This is safe to handle and can be used as an alternative XUID form."""
        return self._xuid_str

    def __str__(self) -> str:
        """Returns a shortened XUID value representation as a string.
        This has a higher risk of collisions and should be handled with care."""
        return self._xuid_str[: XUID.LEN_STR]

    def __eq__(self, other) -> bool:
        """Returns true if both XUIDs represent the same user and salt.
        Raises TypeError when comparing with any type other an XUID, even None.
        Doing that is a severe program error that should not happen."""
        if not isinstance(other, XUID):
            raise TypeError(f"Can't compare a XUID with {type(other).__name__}")
        return self._xuid_raw == other._xuid_raw

    def pretty(self) -> str:
        """Returns a prettified, shortened XUID value string for printing.
        This includes ANSI escape codes and is only meant for logging."""
        color = _color_palette[hash(self) % len(_color_palette)]
        return f"{color}<{self}>{_color_reset}"


################################################################################


class UserStorage:
    """Abstract base class for a key-value storage.

    When a method return True, it means the given user exists in the storage.
    A method returns False to indicate that a user isn't or wasn't stored."""

    def active(self) -> bool:
        """Returns true if the storage is active and can be used.
        Using an inactive storage will most likely cause errors."""
        raise NotImplementedError("UserStorage.active")

    def get(self, xuid: XUID) -> tuple[dict, bool]:
        """Gets the user data if they exist in the storage."""
        raise NotImplementedError("UserStorage.get")

    def put(self, xuid: XUID, data: dict) -> bool:
        """Puts the user data into the storage, overwriting any old data."""
        raise NotImplementedError("UserStorage.put")

    def rem(self, xuid: XUID):
        """Removes the user and their data from the storage.
        Raises a KeyError if the user is not present on the storage."""
        raise NotImplementedError("UserStorage.rem")


class LocalUserStorage(UserStorage):
    """Implements a non-persistent in-memory user storage."""

    def __init__(self):
        self._storage: dict[XUID, dict] = dict()

    def active(self) -> bool:
        return True

    def get(self, xuid: XUID) -> tuple[dict, bool]:
        data = self._storage.get(xuid)
        if data is None:
            return {}, False
        return data, True

    def put(self, xuid: XUID, data: dict) -> bool:
        xuid_in_storage = xuid in self._storage
        self._storage[xuid] = data
        return xuid_in_storage

    def rem(self, xuid: XUID):
        del self._storage[xuid]


class RedisUserStorage(UserStorage):
    """Implements an user storage backed up by a Redis server.

    :param url: redis:// URL of the Redis server. Defaults to localhost.
    :param timeout: Socket timeouts in seconds."""

    DEFAULT_URL = "redis://localhost:6379/"

    EXPIRY_TIME_IN_SECONDS = 30 * 24 * 60 * 60  # Arbitrary

    def __init__(self, url: str = DEFAULT_URL, timeout: float = 30):
        try:
            self._client = redis.from_url(
                url, socket_timeout=timeout, socket_connect_timeout=timeout
            )
            self._client.ping()
        except redis.exceptions.RedisError:
            self._client = None

    def active(self) -> bool:
        return self._client is not None

    def get(self, xuid: XUID) -> tuple[dict, bool]:
        data = self._client.get(repr(xuid))
        if data:
            return json.loads(data), True
        return {}, False

    def put(self, xuid: XUID, data: dict) -> bool:
        xuid_in_storage = self._client.exists(repr(xuid))
        self._client.set(repr(xuid), json.dumps(data))
        return xuid_in_storage

    def rem(self, xuid: XUID):
        if self._client.delete(repr(xuid)) == 0:
            raise KeyError(repr(xuid))


################################################################################


class UserSettings:
    """User Settings manager class.

    :param storage: Any UserStorage instance.
    :param xuid: XUID of the user.
    """

    def __init__(self, storage: UserStorage, xuid: XUID):
        self._storage = storage
        self._xuid = xuid

        self._data, self._exists = self._storage.get(self._xuid)

        if not self._exists:
            self._data["timestamp_first_seen"] = int(_unix_time())

        self._data["version"] = 1

    @property
    def exists(self):
        return self._exists

    @property
    def xuid(self):
        return self._xuid

    #########################

    @property
    def use_nobot(self) -> bool:
        return bool(self._data.get("use_nobot", False))

    @use_nobot.setter
    def use_nobot(self, value):
        self._data["use_nobot"] = bool(value)

    @property
    def use_prefill(self) -> bool:
        return bool(self._data.get("use_prefill", False))

    @use_prefill.setter
    def use_prefill(self, value):
        self._data["use_prefill"] = bool(value)

    @property
    def use_squash(self) -> bool:
        return bool(self._data.get("use_squash", False))

    @use_squash.setter
    def use_squash(self, value):
        self._data["use_squash"] = bool(value)

    #########################

    def last_seen_msg(self) -> str:
        time_now = int(_unix_time())
        timestamp_last_seen = self._data.get("timestamp_last_seen")
        if isinstance(timestamp_last_seen, int):
            return f"last seen {time_now - timestamp_last_seen}s ago"
        return "not seen before"

    def save(self):
        self._data["timestamp_last_seen"] = int(_unix_time())
        self._storage.put(self._xuid, self._data)

    def do_show_banner(self, banner_version):
        last_seen_banner = self._data.get("banner", 0)
        if last_seen_banner != banner_version:
            self._data["banner"] = banner_version
            return True
        return False


################################################################################
