"""Identifier generation.

Every BEACN object has a prefixed, ULID-backed id: ``evt_01J...``, ``con_01J...``.
The prefix is human context; the ULID is 26 lexicographically-sortable
characters whose leading 48 bits are a millisecond timestamp.

`new_id` is *monotonic within a process*: two ids minted in the same millisecond
still compare in creation order, because the random component is incremented
rather than redrawn. That is what lets event replay order by `id` alone with no
separate sequence column — see `docs/ARCHITECTURE.md` §5.
"""

from __future__ import annotations

import os
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32, ULID spec
_lock = threading.Lock()
_last_ms = 0
_last_rand = 0
_RAND_MAX = (1 << 80) - 1


def _encode(value: int, length: int) -> str:
    out = ["0"] * length
    for i in range(length - 1, -1, -1):
        out[i] = _ALPHABET[value & 0x1F]
        value >>= 5
    return "".join(out)


def _ulid() -> str:
    global _last_ms, _last_rand
    with _lock:
        ms = int(time.time() * 1000)
        if ms <= _last_ms:
            # Same or backwards clock: keep the previous timestamp and bump the
            # random field so ordering is preserved.
            ms = _last_ms
            _last_rand = (_last_rand + 1) & _RAND_MAX
            if _last_rand == 0:  # overflowed the 80 bits — step the clock
                ms += 1
                _last_rand = int.from_bytes(os.urandom(10), "big")
        else:
            _last_rand = int.from_bytes(os.urandom(10), "big")
        _last_ms = ms
        return _encode(ms, 10) + _encode(_last_rand, 16)


def new_ulid() -> str:
    """A bare 26-character ULID, monotonic within this process."""
    return _ulid()


def new_id(prefix: str) -> str:
    """A prefixed id, e.g. ``new_id("evt") -> 'evt_01J9Z...'``."""
    return f"{prefix}_{_ulid()}"


def ulid_of(prefixed: str) -> str:
    """The ULID part of a prefixed id, or the input unchanged if there is no prefix."""
    return prefixed.split("_", 1)[1] if "_" in prefixed else prefixed


# Prefixes used across the platform, in one place so they cannot drift.
EVENT = "evt"
CONNECTION = "con"
PRODUCER = "prd"
APIKEY = "bk"
TOPIC = "top"
SUBSCRIPTION = "sub"
TASK = "tsk"
NOTIFICATION = "ntf"
AUDIT = "aud"
DELIVERY = "dlv"
CORRELATION = "cor"
REQUEST = "req"
