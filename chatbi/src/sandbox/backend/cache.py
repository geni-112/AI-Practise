import hashlib
import time
from typing import Any

_cache: dict[str, tuple[Any, float]] = {}
TTL = 1800  # 30 minutes

def _key(question: str) -> str:
    return hashlib.md5(question.strip().lower().encode()).hexdigest()

def get(question: str) -> Any | None:
    k = _key(question)
    if k in _cache:
        value, ts = _cache[k]
        if time.time() - ts < TTL:
            return value
        del _cache[k]
    return None

def set(question: str, value: Any) -> None:
    _cache[_key(question)] = (value, time.time())
