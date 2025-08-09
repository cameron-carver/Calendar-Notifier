from __future__ import annotations

import json
from typing import Any, Optional
import asyncio

import redis.asyncio as redis

from app.core.config import settings


class RedisCache:
    """Tiny async Redis cache facade for JSON-serializable objects."""

    _client: Optional[redis.Redis] = None

    @classmethod
    def client(cls) -> redis.Redis:
        if cls._client is None:
            cls._client = redis.from_url(settings.redis_url, decode_responses=True)
        return cls._client

    @classmethod
    async def get_json(cls, key: str) -> Optional[Any]:
        value = await cls.client().get(key)
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
            # As a fallback, convert non-serializable objects to dict via str()
            payload = json.dumps({"_": str(value)})
        await cls.client().set(key, payload, ex=ttl_seconds)


def make_key(*parts: str) -> str:
    return ":".join(parts)

