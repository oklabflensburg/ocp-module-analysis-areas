"""Small JSON cache helper using module-scoped public SDK ports."""

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar

from app.platform.modules.sdk import CachePort

_last_status: ContextVar[str | None] = ContextVar("analysis_areas_cache_status", default=None)


def cache_status() -> str | None:
    return _last_status.get()


def cache_key(name: str, parameters: Mapping[str, object], *, generation: str) -> str:
    encoded = json.dumps(
        parameters, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    digest = hashlib.sha256(encoded).hexdigest()[:24]
    return f"{name}:v{generation}:{digest}"


async def get_or_compute[T](
    cache: CachePort,
    key: str,
    *,
    ttl_seconds: int,
    compute: Callable[[], Awaitable[T]],
) -> T:
    cached = await cache.get(key)
    if cached is not None:
        _last_status.set("HIT")
        return json.loads(cached)
    value = await compute()
    await cache.set(
        key,
        json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode(),
        ttl_seconds=ttl_seconds,
    )
    _last_status.set("MISS")
    return value
