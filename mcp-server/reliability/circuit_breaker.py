import functools
import logging
import time
from typing import Any, Callable, Dict, Optional
from reliability.cache import get_cached_value, make_cache_key

logger = logging.getLogger("mcp_reliability.circuit_breaker")


class CircuitBreakerOpenException(Exception):
    """Exception raised when calling a service whose circuit breaker is OPEN."""
    pass


class CircuitBreaker:
    """Circuit Breaker monitoring upstream health and short-circuiting dead services."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_count = 0
        self.last_state_change = time.time()

    def record_success(self):
        """Record successful invocation."""
        if self.state != "CLOSED":
            logger.info(f"[CircuitBreaker:{self.name}] Upstream recovered! State -> CLOSED")
            self.state = "CLOSED"
        self.failure_count = 0
        self.last_state_change = time.time()

    def record_failure(self):
        """Record failed invocation."""
        self.failure_count += 1
        logger.warning(
            f"[CircuitBreaker:{self.name}] Failure {self.failure_count}/{self.failure_threshold}"
        )
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.last_state_change = time.time()
            logger.error(
                f"[CircuitBreaker:{self.name}] Failure threshold reached! Circuit TRIP -> OPEN (for {self.recovery_timeout}s)"
            )

    def allow_request(self) -> bool:
        """Check if request is allowed based on current circuit breaker state."""
        now = time.time()
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            if now - self.last_state_change >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                self.last_state_change = now
                logger.info(
                    f"[CircuitBreaker:{self.name}] Recovery timeout elapsed. State -> HALF_OPEN (testing recovery)"
                )
                return True
            return False

        if self.state == "HALF_OPEN":
            return True

        return True


# Global registry of circuit breakers per upstream API
_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, failure_threshold: int = 3, recovery_timeout: float = 30.0) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, failure_threshold, recovery_timeout)
    return _breakers[name]


def with_circuit_breaker(upstream_name: str, failure_threshold: int = 3, recovery_timeout: float = 30.0) -> Callable:
    """Decorator wrapping API calls in a per-upstream CircuitBreaker.

    When tripped OPEN, attempts to return the last cached value or a degraded response dict.
    """
    def decorator(func: Callable) -> Callable:
        breaker = get_circuit_breaker(upstream_name, failure_threshold, recovery_timeout)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check circuit breaker state
            if not breaker.allow_request():
                logger.warning(
                    f"[CircuitBreaker:{upstream_name}] TRIP! Short-circuiting call to '{func.__name__}'."
                )

                # Attempt fallback to last cached value
                cache_key = make_cache_key(func.__name__, kwargs)
                cached_val = get_cached_value(cache_key)
                if cached_val is not None:
                    if isinstance(cached_val, dict):
                        res = dict(cached_val)
                        res["_circuit_degraded"] = True
                        res["_degraded_reason"] = f"Circuit breaker OPEN for {upstream_name}"
                        return res
                    return cached_val

                # Degraded fallback response
                return {
                    "error": f"Upstream service '{upstream_name}' is currently unavailable (Circuit Breaker OPEN)",
                    "degraded": True,
                    "upstream": upstream_name,
                }

            # Execute tool call
            try:
                result = func(*args, **kwargs)
                if isinstance(result, dict) and "error" in result:
                    breaker.record_failure()
                else:
                    breaker.record_success()
                return result

            except Exception as exc:
                breaker.record_failure()
                raise exc

        return wrapper

    return decorator
