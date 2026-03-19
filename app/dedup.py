import hashlib
import time

_seen: dict[str, float] = {}
_WINDOW = 10.0


def _key(url: str, payload: str) -> str:
    return hashlib.sha256(f"{url}|{payload}".encode()).hexdigest()


async def is_duplicate(url: str, payload: str) -> bool:
    k = _key(url, payload)
    now = time.monotonic()
    return k in _seen and now - _seen[k] < _WINDOW


async def mark_seen(url: str, payload: str):
    k = _key(url, payload)
    _seen[k] = time.monotonic()
    now = time.monotonic()
    expired = [key for key, ts in list(_seen.items()) if now - ts >= _WINDOW]
    for key in expired:
        del _seen[key]
