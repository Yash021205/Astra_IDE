"""
Cache / warm-pool registry (tech-stack §9: "Cache: Redis — sessions, warm pool
registry").

A tiny key/value layer backed by Redis when REDIS_URL is reachable, falling
back to an in-process dict otherwise. The fallback keeps dev working with no
Redis running; in a real deployment the same code uses Redis so cache and the
prewarm pool are shared across API replicas.
"""
from __future__ import annotations

import time
from typing import Optional

from app.core.config import get_settings

settings = get_settings()


class Cache:
    def __init__(self, url: str):
        self._mem: dict[str, tuple[str, float]] = {}   # key -> (value, expires_at)
        self._r = None
        try:
            import redis
            r = redis.from_url(url, socket_connect_timeout=0.3, socket_timeout=0.3,
                               decode_responses=True)
            r.ping()
            self._r = r
        except Exception:
            self._r = None                              # graceful: in-memory

    @property
    def backend(self) -> str:
        return "redis" if self._r is not None else "memory"

    def get(self, key: str) -> Optional[str]:
        if self._r is not None:
            try:
                return self._r.get(key)
            except Exception:
                self._r = None                          # demote on failure
        v = self._mem.get(key)
        if not v:
            return None
        value, exp = v
        if exp and exp < time.time():
            self._mem.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl: int = 0) -> None:
        if self._r is not None:
            try:
                self._r.set(key, value, ex=ttl or None)
                return
            except Exception:
                self._r = None
        self._mem[key] = (value, time.time() + ttl if ttl else 0.0)

    def incr(self, key: str) -> int:
        if self._r is not None:
            try:
                return int(self._r.incr(key))
            except Exception:
                self._r = None
        cur = int(self.get(key) or 0) + 1
        self.set(key, str(cur))
        return cur


_cache: Optional[Cache] = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache(settings.redis_url)
    return _cache
