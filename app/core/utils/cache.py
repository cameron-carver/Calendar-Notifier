from __future__ import annotations

import json
from typing import Any, Optional
import asyncio

import redis.asyncio as redis_async
import redis as redis_sync

from app.core.config import settings


class RedisCache:
    """Redis cache facade supporting both async and sync access."""

    _client_async: Optional[redis_async.Redis] = None
    _client_sync: Optional[redis_sync.Redis] = None

    @classmethod
    def client_async(cls) -> redis_async.Redis:
        if cls._client_async is None:
            cls._client_async = redis_async.from_url(settings.redis_url, decode_responses=True)
        return cls._client_async

    @classmethod
    def client_sync(cls) -> redis_sync.Redis:
        if cls._client_sync is None:
            cls._client_sync = redis_sync.from_url(settings.redis_url, decode_responses=True)
        return cls._client_sync

    # -------- Async helpers --------
    @classmethod
    async def get_json(cls, key: str) -> Optional[Any]:
        value = await cls.client_async().get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except Exception:
            return None

    @classmethod
    async def set_json(cls, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            payload = json.dumps(value)
        except TypeError:
            payload = json.dumps({"_": str(value)})
        await cls.client_async().set(key, payload, ex=ttl_seconds)

    # -------- Sync helpers --------
    @classmethod
    def get_json_sync(cls, key: str) -> Optional[Any]:
        value = cls.client_sync().get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except Exception:
            return None

    @classmethod
    def set_json_sync(cls, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            payload = json.dumps(value)
        except TypeError:
            payload = json.dumps({"_": str(value)})
        cls.client_sync().set(key, payload, ex=ttl_seconds)


def make_key(*parts: str) -> str:
    return ":".join(parts)

