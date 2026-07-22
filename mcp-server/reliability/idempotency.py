import functools
import logging
from typing import Any, Callable, Optional
from reliability.cache import get_cached_value, set_cached_value

logger = logging.getLogger("mcp_reliability.idempotency")


def make_idempotency_cache_key(idempotency_key: str) -> str:
    """Format key for idempotency tracking."""
    return f"mcp:idempotency:{idempotency_key}"


def with_idempotency(ttl_seconds: int = 86400) -> Callable:
    """Decorator checking for optional 'idempotency_key' in kwargs.

    If idempotency_key is provided and has been processed within the TTL window,
    short-circuits and returns the previously stored execution result.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            idempotency_key = kwargs.get("idempotency_key")
            if not idempotency_key:
                return func(*args, **kwargs)

            cache_key = make_idempotency_cache_key(idempotency_key)
            existing = get_cached_value(cache_key)

            if existing is not None:
                logger.info(
                    f"[Idempotency] HIT for key '{idempotency_key}'. Returning stored result."
                )
                if isinstance(existing, dict):
                    res = dict(existing)
                    res["_idempotent"] = True
                    return res
                return existing

            # Execute tool call
            result = func(*args, **kwargs)

            # Store result if valid (non-error)
            if not (isinstance(result, dict) and "error" in result):
                set_cached_value(cache_key, result, ttl_seconds)
                logger.debug(
                    f"[Idempotency] STORED result for key '{idempotency_key}' (TTL: {ttl_seconds}s)."
                )

            return result

        return wrapper

    return decorator
