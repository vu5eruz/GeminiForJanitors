"""X-Unique/User Identifier (XUID) and User Settings/Storage.

XUIDs are a mechanism to anonymously identify unique users from sensitive data.
The proxy has no access to any user-unique data or info except their API keys.
Hashing an API key with a secret salt gives an unique user ID for program use.
"""

from base64 import urlsafe_b64encode as _base64
from colorama.ansi import Fore as _colorama_ansi_fore
from hashlib import sha256 as _hash_fun  # Choice of hash function is arbitrary
from hmac import digest as _hmac_digest

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
    """

    LEN_REPR = len("xuid:") + (4 * _hash_fun().digest_size + 2) // 3
    LEN_STR = 8  # Arbitrary, could be made a global proxy settings

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
        return f"xuid:{self._xuid_str}"

    def __str__(self) -> str:
        """Returns a shortened XUID value representation as a string.
        This has a higher risk of collisions and should be handled with care."""
        return self._xuid_str[: XUID.LEN_STR]

    def __eq__(self, other) -> bool:
        if not isinstance(other, XUID):
            # This SHOULD NOT happen, raise a hard and explicit error
            raise TypeError(f"Can't compare a XUID with {type(other).__name__}")
        return self._xuid_raw == other._xuid_raw

    def __ne__(self, other) -> bool:
        if not isinstance(other, XUID):
            # This SHOULD NOT happen, raise a hard and explicit error
            raise TypeError(f"Can't compare a XUID with {type(other).__name__}")
        return self._xuid_raw != other._xuid_raw

    def pretty(self) -> str:
        """Returns a prettified, shortened XUID value string for printing.
        This includes ANSI escape codes and is not meant for processing."""
        color = _color_palette[hash(self) % len(_color_palette)]
        return f"{color}<{self}>{_color_reset}"


################################################################################


class UserSettings:
    pass  # TODO


################################################################################


class UserStorage:
    """Abstract base class for a key-value storage.

    When a method return True, it means the given user exists in the storage.
    A method return False to indicate that a user isn't or wasn't stored."""

    def get(self, xuid: XUID) -> tuple[dict, bool]:
        """Gets the user data if they exist in the storage."""
        raise NotImplementedError("UserStorage.get")

    def put(self, xuid: XUID, data: dict) -> bool:
        """Puts the user data in the storage, overwriting any old data."""
        raise NotImplementedError("UserStorage.put")

    def rem(self, xuid: XUID):
        """Removes the user and their data from the storage.
        Raises a KeyError if the user is not present on the storage."""
        raise NotImplementedError("UserStorage.rem")


class LocalUserStorage(UserStorage):
    """Implements a non-persistent in-memory storage."""

    def __init__(self):
        self._storage: dict[XUID, dict] = dict()

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
    pass  # TODO


################################################################################
