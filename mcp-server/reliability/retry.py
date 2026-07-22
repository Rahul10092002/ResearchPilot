import functools
import logging
import random
import time
from typing import Any, Callable, Tuple, Type

logger = logging.getLogger("mcp_reliability.retry")


def with_retry(
    max_attempts: int = 3,
    backoff_base: float = 0.5,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    retry_on_error_dict: bool = True,
) -> Callable:
    """Decorator applying exponential backoff with jitter around API calls."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 1
            last_result = None
            last_exception = None

            while attempt <= max_attempts:
                try:
                    result = func(*args, **kwargs)

                    if (
                        retry_on_error_dict
                        and isinstance(result, dict)
                        and "error" in result
                        and attempt < max_attempts
                    ):
                        err_msg = result.get("error", "Unknown error dict returned")
                        calculated_delay = backoff_base * (backoff_factor ** (attempt - 1))
                        actual_delay = (
                            random.uniform(0, calculated_delay) if jitter else calculated_delay
                        )

                        logger.warning(
                            f"[Retry] Attempt {attempt}/{max_attempts} for '{func.__name__}' returned error: '{err_msg}'. "
                            f"Retrying in {actual_delay:.2f}s..."
                        )
                        time.sleep(actual_delay)
                        attempt += 1
                        last_result = result
                        continue

                    return result

                except retry_exceptions as exc:
                    last_exception = exc
                    if attempt >= max_attempts:
                        logger.error(
                            f"[Retry] Attempt {attempt}/{max_attempts} for '{func.__name__}' failed with exception: {exc}. "
                            f"Max attempts reached."
                        )
                        raise exc

                    calculated_delay = backoff_base * (backoff_factor ** (attempt - 1))
                    actual_delay = (
                        random.uniform(0, calculated_delay) if jitter else calculated_delay
                    )

                    logger.warning(
                        f"[Retry] Attempt {attempt}/{max_attempts} for '{func.__name__}' failed with exception: {exc}. "
                        f"Retrying in {actual_delay:.2f}s..."
                    )
                    time.sleep(actual_delay)
                    attempt += 1

            if last_exception:
                raise last_exception
            return last_result

        return wrapper

    return decorator
