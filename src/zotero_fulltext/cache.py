"""Small in-memory cache helpers."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Generic, TypeVar


K = TypeVar("K")
V = TypeVar("V")


@dataclass
class _CacheValue(Generic[V]):
    expires_at: float
    value: V


class TTLCache(Generic[K, V]):
    """A tiny TTL/LRU cache implemented with the standard library.

    Thread-safe: MCP SDK 2.x runs sync tool handlers on worker threads, so
    the cache can be hit concurrently.
    """

    def __init__(self, maxsize: int, ttl_seconds: int) -> None:
        self.maxsize = max(1, maxsize)
        self.ttl_seconds = max(1, ttl_seconds)
        self._entries: "OrderedDict[K, _CacheValue[V]]" = OrderedDict()
        self._lock = Lock()

    def clear(self) -> None:
        """Remove all cache entries."""
        with self._lock:
            self._entries.clear()

    def delete(self, key: K) -> None:
        """Remove a single cache entry if present."""
        with self._lock:
            self._entries.pop(key, None)

    def get(self, key: K) -> V | None:
        """Retrieve a cached value when present and not expired."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= monotonic():
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return entry.value

    def set(self, key: K, value: V) -> None:
        """Store a value in the cache."""
        with self._lock:
            self._purge_expired()
            self._entries[key] = _CacheValue(monotonic() + self.ttl_seconds, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.maxsize:
                self._entries.popitem(last=False)

    def _purge_expired(self) -> None:
        now = monotonic()
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)
