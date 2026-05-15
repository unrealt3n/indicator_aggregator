"""
In-memory TTL cache to avoid hammering APIs.
"""

import time
from typing import Any, Optional


class Cache:
    """Simple dict-based cache with per-key TTL."""

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        ttl = ttl or self._default_ttl
        self._store[key] = (time.time() + ttl, value)

    def clear(self):
        self._store.clear()


# Global cache instance
cache = Cache()
