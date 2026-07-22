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
@with_cache(ttl_seconds=3600, tool_name="get_company_fundamentals")
@with_retry(max_attempts=3, backoff_base=0.5, jitter=True)
def get_company_fundamentals(ticker: str, idempotency_key: str = None) -> Dict[str, Any]:
    """Fetch fundamental metrics (P/E ratio, market cap, EPS, margins) for a company ticker.

    Uses safe dictionary extraction (.get) to prevent crashes when metrics are missing.
    Returns a structured JSON dictionary of fundamental financial metrics.
    """
    clean_ticker = ticker.strip().upper()
    if not clean_ticker:
        return {"error": "Ticker symbol cannot be empty", "ticker": ticker}

    try:
        t = yf.Ticker(clean_ticker)
        info = getattr(t, "info", {}) or {}

        if not info or not isinstance(info, dict) or ("symbol" not in info and "shortName" not in info and "longName" not in info):
            # Check fast_info as fallback for minimal data if info is empty
            fast_info = getattr(t, "fast_info", None)
            if fast_info is None or not getattr(fast_info, "market_cap", None):
                return {
                    "error": f"Failed to fetch fundamental data for ticker '{clean_ticker}'",
                    "ticker": clean_ticker,
                }

        # Safe extraction helper
        def safe_num(val):
            if val is None or (isinstance(val, float) and val != val):
                return None
            return val

        company_name = info.get("longName") or info.get("shortName") or clean_ticker

        return {
            "ticker": clean_ticker,
            "company_name": company_name,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": safe_num(info.get("marketCap")),
            "pe_ratio": safe_num(info.get("trailingPE")),
            "forward_pe": safe_num(info.get("forwardPE")),
            "eps": safe_num(info.get("trailingEps")),
            "revenue": safe_num(info.get("totalRevenue")),
            "profit_margins": safe_num(info.get("profitMargins")),
            "dividend_yield": safe_num(info.get("dividendYield")),
            "fifty_two_week_high": safe_num(info.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": safe_num(info.get("fiftyTwoWeekLow")),
            "currency": info.get("currency", "USD"),
        }

    except Exception as exc:
        logger.error(f"Unexpected error fetching fundamentals for {clean_ticker}: {exc}")
        return {
            "error": f"Error fetching fundamentals for ticker '{clean_ticker}': {str(exc)}",
            "ticker": clean_ticker,
        }
