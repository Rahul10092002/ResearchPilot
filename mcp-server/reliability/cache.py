import functools
import hashlib
import json
import logging
import os
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("mcp_reliability.cache")

# Global in-memory fallback cache: {key: (value, expire_at_timestamp)}
_memory_cache: Dict[str, Tuple[Any, float]] = {}
_redis_client = None
_redis_checked = False


def _get_redis_client():
    """Lazily initialize Redis client with local fallback handling."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client

    primary_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    urls_to_try = [primary_url]
    if "redis://redis:" in primary_url:
        urls_to_try.append(primary_url.replace("redis://redis:", "redis://localhost:"))
        urls_to_try.append(primary_url.replace("redis://redis:", "redis://127.0.0.1:"))
    elif "localhost" not in primary_url and "127.0.0.1" not in primary_url:
        urls_to_try.append("redis://localhost:6379/0")

    import redis

    for url in urls_to_try:
        try:
            client = redis.Redis.from_url(url, socket_timeout=2.0, socket_connect_timeout=2.0)
            client.ping()
            _redis_client = client
            logger.info(f"[Cache] Connected to Redis at {url}")
            _redis_checked = True
            return _redis_client
        except Exception as err:
            logger.debug(f"[Cache] Could not connect to Redis at {url}: {err}")

    logger.warning(
        "[Cache] Could not connect to any Redis instance. Seamlessly falling back to in-memory dictionary cache."
    )
    _redis_checked = True
    return None


def make_cache_key(tool_name: str, kwargs: dict) -> str:
    """Generate a deterministic SHA-256 cache key from tool_name and sorted kwargs."""
    clean_kwargs = {k: v for k, v in kwargs.items() if k != "idempotency_key"}
    serialized = json.dumps(clean_kwargs, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"mcp:cache:{tool_name}:{digest}"


def get_cached_value(key: str) -> Optional[Any]:
    """Retrieve value from Redis or in-memory fallback cache."""
    client = _get_redis_client()
    if client:
        try:
            val = client.get(key)
            if val is not None:
                logger.info(f"[Cache HIT] Redis key='{key}'")
                return json.loads(val.decode("utf-8"))
        except Exception as err:
            logger.warning(f"[Cache ERROR] Redis get failed ({err}), switching to memory cache.")

    now = time.time()
    if key in _memory_cache:
        val, expire_at = _memory_cache[key]
        if expire_at > now:
            logger.info(f"[Cache HIT] Memory key='{key}'")
            return val
        else:
            del _memory_cache[key]

    logger.info(f"[Cache MISS] key='{key}'")
    return None


def set_cached_value(key: str, value: Any, ttl_seconds: int) -> None:
    """Store value in Redis and in-memory fallback cache."""
    _memory_cache[key] = (value, time.time() + ttl_seconds)

    client = _get_redis_client()
    if client:
        try:
            serialized = json.dumps(value)
            client.setex(key, ttl_seconds, serialized)
            logger.info(f"[Cache STORED] Redis key='{key}' ttl={ttl_seconds}s")
        except Exception as err:
            logger.warning(f"[Cache ERROR] Redis set error ({err}).")


def with_cache(ttl_seconds: int = 900, tool_name: Optional[str] = None) -> Callable:
    """Decorator wrapping tool calls in a TTL cache keyed on (tool_name, sorted(kwargs))."""

    def decorator(func: Callable) -> Callable:
        name = tool_name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = make_cache_key(name, kwargs)

            cached_val = get_cached_value(cache_key)
            if cached_val is not None:
                if isinstance(cached_val, dict):
                    res = dict(cached_val)
                    res["_cached"] = True
                    return res
                return cached_val

            result = func(*args, **kwargs)

            if isinstance(result, dict) and "error" in result:
                return result

            set_cached_value(cache_key, result, ttl_seconds)
            return result

        return wrapper

    return decorator
