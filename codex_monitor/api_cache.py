from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from .api_timing import logger, timed_dependency

try:
    import redis
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    class _MissingRedis:
        @staticmethod
        def from_url(*_: Any, **__: Any) -> Any:
            raise _MissingRedisError("redis is not installed")

    class _MissingRedisError(Exception):
        pass

    redis = SimpleNamespace(RedisError=_MissingRedisError)
    aioredis = SimpleNamespace(Redis=_MissingRedis)

CACHE_KEY_PREFIX = os.environ.get("CACHE_KEY_PREFIX", "codex-monitor")
CACHE_MEMORY_FALLBACK_MODE = os.environ.get("CACHE_MEMORY_FALLBACK_MODE", "single-worker")
MONITOR_API_WORKERS = int(os.environ.get("MONITOR_API_WORKERS", "1"))
VALID_FALLBACK_MODES = {"single-worker", "always", "disabled"}


class JsonCache:
    def __init__(
        self,
        url: str,
        key_prefix: str = CACHE_KEY_PREFIX,
        memory_fallback_mode: str = CACHE_MEMORY_FALLBACK_MODE,
        worker_count: int = MONITOR_API_WORKERS,
    ):
        self.url = url
        self.key_prefix = key_prefix.strip(":")
        self.memory_fallback_mode = self._fallback_mode(memory_fallback_mode)
        self.worker_count = max(int(worker_count or 1), 1)
        self.memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self.client: Any | None = None
        self.remote_dirty = False
        self.last_error: str | None = None

    @staticmethod
    def _fallback_mode(value: str) -> str:
        mode = str(value or "single-worker").strip().lower()
        if mode not in VALID_FALLBACK_MODES:
            logger.warning("cache_invalid_fallback_mode mode=%s default=single-worker", value)
            return "single-worker"
        return mode

    @property
    def memory_fallback_allowed(self) -> bool:
        if self.memory_fallback_mode == "always":
            return True
        if self.memory_fallback_mode == "disabled":
            return False
        return self.worker_count == 1

    def cache_key(self, key: str) -> str:
        if not self.key_prefix:
            return key
        return f"{self.key_prefix}:{key}"

    async def _get_client(self) -> Any | None:
        if self.client is not None:
            return self.client
        client: Any | None = None
        try:
            client = aioredis.Redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=1.0,
            )
            with timed_dependency("cache.valkey.ping"):
                await client.ping()
            self.client = client
            self.last_error = None
            return client
        except redis.RedisError as exc:
            if client is not None:
                try:
                    await client.aclose()
                except Exception as close_exc:
                    logger.debug("cache.valkey.close_failed error=%s", close_exc)
            self.last_error = str(exc)
            self.client = None
            return None

    async def _drop_client(self) -> None:
        client = self.client
        self.client = None
        if client is None:
            return
        try:
            await client.aclose()
        except Exception as exc:
            logger.debug("cache.valkey.close_failed error=%s", exc)

    async def _clear_remote(self, client: Any) -> bool:
        try:
            with timed_dependency("cache.valkey.clear"):
                async for key in client.scan_iter(match=f"{self.cache_key('*')}"):
                    await client.delete(key)
            self.last_error = None
            return True
        except redis.RedisError as exc:
            self.last_error = str(exc)
            await self._drop_client()
            return False

    async def _remote_ready(self) -> Any | None:
        client = await self._get_client()
        if client is None:
            return None
        return client

    def _memory_get(self, key: str) -> dict[str, Any] | None:
        with timed_dependency("cache.memory.get", key=key):
            value = self.memory.get(key)
            if not value:
                return None
            expires_at, data = value
            if expires_at < datetime.now(timezone.utc).timestamp():
                self.memory.pop(key, None)
                return None
            return data

    def _memory_set(self, key: str, data: dict[str, Any], ttl_seconds: int) -> None:
        with timed_dependency("cache.memory.set", key=key, ttl=ttl_seconds):
            expires_at = datetime.now(timezone.utc).timestamp() + ttl_seconds
            self.memory[key] = (expires_at, data)

    def _fallback_status(self) -> dict[str, Any]:
        if self.memory_fallback_allowed:
            status = {"backend": "memory", "ok": True, "key_prefix": self.key_prefix}
        else:
            status = {
                "backend": "disabled",
                "ok": False,
                "key_prefix": self.key_prefix,
                "reason": "memory fallback is not allowed for this worker configuration",
            }
        status["memory_fallback_mode"] = self.memory_fallback_mode
        status["worker_count"] = self.worker_count
        if self.remote_dirty:
            status["remote_dirty"] = True
        if self.last_error:
            status["fallback_reason"] = self.last_error
        return status

    async def get(self, key: str) -> dict[str, Any] | None:
        namespaced_key = self.cache_key(key)
        client = await self._remote_ready()
        if client is not None:
            try:
                with timed_dependency("cache.valkey.get", key=namespaced_key):
                    value = await client.get(namespaced_key)
                if value:
                    return json.loads(value)
                return None
            except json.JSONDecodeError:
                logger.warning("cache_decode_failed key=%s", namespaced_key)
                try:
                    await client.delete(namespaced_key)
                except redis.RedisError:
                    await self._drop_client()
                return None
            except redis.RedisError as exc:
                self.last_error = str(exc)
                await self._drop_client()

        if not self.memory_fallback_allowed:
            return None
        return self._memory_get(namespaced_key)

    async def set(self, key: str, data: dict[str, Any], ttl_seconds: int) -> None:
        namespaced_key = self.cache_key(key)
        encoded = json.dumps(data, sort_keys=True)
        client = await self._remote_ready()
        if client is not None:
            try:
                with timed_dependency("cache.valkey.set", key=namespaced_key, ttl=ttl_seconds):
                    await client.setex(namespaced_key, ttl_seconds, encoded)
                return
            except redis.RedisError as exc:
                self.last_error = str(exc)
                await self._drop_client()

        if self.memory_fallback_allowed:
            self._memory_set(namespaced_key, data, ttl_seconds)

    async def clear(self) -> None:
        with timed_dependency("cache.memory.clear"):
            self.memory.clear()

        client = await self._get_client()
        if client is None:
            self.remote_dirty = True
            return
        if await self._clear_remote(client):
            self.remote_dirty = False
        else:
            self.remote_dirty = True

    async def status(self) -> dict[str, Any]:
        client = await self._remote_ready()
        if client is None:
            with timed_dependency("cache.memory.status"):
                return self._fallback_status()
        try:
            with timed_dependency("cache.valkey.status"):
                info = await client.info("persistence")
            status = {
                "backend": "valkey",
                "ok": True,
                "key_prefix": self.key_prefix,
                "aof_enabled": bool(info.get("aof_enabled")),
                "rdb_changes_since_last_save": info.get("rdb_changes_since_last_save"),
                "memory_fallback_mode": self.memory_fallback_mode,
                "worker_count": self.worker_count,
            }
            return status
        except redis.RedisError as exc:
            self.last_error = str(exc)
            await self._drop_client()
            with timed_dependency("cache.memory.status"):
                return self._fallback_status()

    async def aclose(self) -> None:
        await self._drop_client()
