import contextvars
import datetime
import functools
import logging
import sys
import time
import uuid
from typing import Any, Callable, Optional

# Context variable to hold the current request UUID across function calls
current_req_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_req_id", default="system")


class MCPISOFormatter(logging.Formatter):
    """Logging Formatter outputting ISO-8601 UTC timestamps with millisecond precision and request UUID tags."""

    def format(self, record: logging.LogRecord) -> str:
        # Generate ISO-8601 UTC timestamp with millisecond precision
        now = datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc)
        iso_ts = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        req_id = current_req_id.get("system")
        level = record.levelname

        message = record.getMessage()
        return f"{iso_ts} [{level}] [research-pilot] [req_id:{req_id}] {record.name}: {message}"


def setup_mcp_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure root and package loggers to use MCPISOFormatter printing to stderr."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(MCPISOFormatter())
    root_logger.addHandler(stream_handler)

    return logging.getLogger("mcp_server")


def get_current_req_id() -> str:
    return current_req_id.get("system")


def trace_tool_call(tool_name: Optional[str] = None) -> Callable:
    """Decorator generating a unique request UUID for each tool call and tracking execution lifecycle."""

    def decorator(func: Callable) -> Callable:
        name = tool_name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Generate or reuse UUID
            req_id = kwargs.pop("request_id", None) or str(uuid.uuid4())[:8]
            token = current_req_id.set(req_id)

            logger = logging.getLogger(f"mcp_tools.{name}")
            start_time = time.perf_counter()

            # Clean arguments for clean logging
            log_kwargs = {k: v for k, v in kwargs.items() if k not in ("idempotency_key",)}
            logger.info(f"Tool execution STARTED: tool='{name}' params={log_kwargs}")

            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                if isinstance(result, dict) and "error" in result:
                    logger.warning(
                        f"Tool execution COMPLETED WITH ERROR: tool='{name}' duration={elapsed_ms:.1f}ms error='{result.get('error')}'"
                    )
                else:
                    summary = ""
                    if isinstance(result, dict):
                        if "price" in result:
                            summary = f"price={result.get('price')} {result.get('currency')}"
                        elif "count" in result:
                            summary = f"articles_count={result.get('count')}"
                        elif "company_name" in result:
                            summary = f"company='{result.get('company_name')}' cap={result.get('market_cap')}"

                    logger.info(
                        f"Tool execution COMPLETED: tool='{name}' status=SUCCESS duration={elapsed_ms:.1f}ms {summary}".strip()
                    )

                return result

            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                logger.error(
                    f"Tool execution FAILED: tool='{name}' duration={elapsed_ms:.1f}ms exception='{exc}'"
                )
                raise exc

            finally:
                current_req_id.reset(token)

        return wrapper

    return decorator
