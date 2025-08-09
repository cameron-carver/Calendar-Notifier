import asyncio
import random
from typing import Callable, Type, Tuple, Any


def should_retry_http_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    transient_markers = [
        "rate limit", "429", "backenderror", "backend error", "internal error",
        "temporarily unavailable", "reset reason", "connection reset",
    ]
    return any(m in msg for m in transient_markers)


def async_retry(
    exceptions: Tuple[Type[BaseException], ...],
    tries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    should_retry: Callable[[BaseException], bool] | None = None,
):
    def decorator(func: Callable[..., Any]):
        async def wrapper(*args, **kwargs):
            attempt = 0
            delay = base_delay
            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:  # type: ignore
                    attempt += 1
                    if attempt >= tries or (should_retry and not should_retry(exc)):
                        raise
                    await asyncio.sleep(delay + random.uniform(0, delay / 2))
                    delay = min(delay * 2, max_delay)
        return wrapper
    return decorator


def retry(
    exceptions: Tuple[Type[BaseException], ...],
    tries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    should_retry: Callable[[BaseException], bool] | None = None,
):
    def decorator(func: Callable[..., Any]):
        def wrapper(*args, **kwargs):
            attempt = 0
            delay = base_delay
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # type: ignore
                    attempt += 1
                    if attempt >= tries or (should_retry and not should_retry(exc)):
                        raise
                    asyncio.sleep(delay + random.uniform(0, delay / 2))
                    delay = min(delay * 2, max_delay)
        return wrapper
    return decorator

