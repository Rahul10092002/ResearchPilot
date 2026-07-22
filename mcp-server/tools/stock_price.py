from datetime import datetime, timezone
import logging
from typing import Any, Dict
import yfinance as yf

from reliability.cache import with_cache
from reliability.circuit_breaker import with_circuit_breaker
from reliability.idempotency import with_idempotency
from reliability.retry import with_retry

logger = logging.getLogger(__name__)


@with_idempotency(ttl_seconds=86400)
@with_circuit_breaker(upstream_name="yfinance", failure_threshold=3, recovery_timeout=30.0)
@with_cache(ttl_seconds=900, tool_name="get_stock_price")
@with_retry(max_attempts=3, backoff_base=0.5, jitter=True)
def get_stock_price(ticker: str, idempotency_key: str = None) -> Dict[str, Any]:
    """Fetch current or latest stock price for a given ticker symbol.

    Primary lookup uses yfinance fast_info, falling back to 1-day historical data.
    Returns structured dict with ticker, price, currency, and UTC timestamp,
    or a structured error dict on failure.
    """
    clean_ticker = ticker.strip().upper()
    if not clean_ticker:
        return {"error": "Ticker symbol cannot be empty", "ticker": ticker}

    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        t = yf.Ticker(clean_ticker)

        # 1. Primary approach: fast_info
        price = None
        currency = "USD"

        try:
            fast_info = getattr(t, "fast_info", None)
            if fast_info is not None:
                price = fast_info.get("lastPrice") or fast_info.get("last_price")
                currency = fast_info.get("currency", "USD")
        except Exception as e:
            logger.debug(f"fast_info lookup failed for {clean_ticker}: {e}")

        # 2. Fallback approach: 1-day history
        if price is None or (isinstance(price, float) and (price != price or price <= 0)):
            try:
                hist = t.history(period="1d")
                if not hist.empty and "Close" in hist.columns:
                    latest_close = hist["Close"].iloc[-1]
                    if float(latest_close) > 0:
                        price = float(latest_close)
            except Exception as e:
                logger.debug(f"history fallback failed for {clean_ticker}: {e}")

        # 3. Validation check
        if price is None or (isinstance(price, float) and price != price):
            return {
                "error": f"Failed to fetch price data for ticker '{clean_ticker}'",
                "ticker": clean_ticker,
            }

        return {
            "ticker": clean_ticker,
            "price": round(float(price), 4),
            "currency": str(currency),
            "timestamp": timestamp,
        }

    except Exception as exc:
        logger.error(f"Unexpected error fetching stock price for {clean_ticker}: {exc}")
        return {
            "error": f"Error fetching price data for ticker '{clean_ticker}': {str(exc)}",
            "ticker": clean_ticker,
        }
