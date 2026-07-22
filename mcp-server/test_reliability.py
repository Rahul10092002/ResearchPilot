import json
import logging
import time
from reliability.cache import get_cached_value, make_cache_key
from reliability.circuit_breaker import get_circuit_breaker
from reliability.logging_config import setup_mcp_logging
from reliability.retry import with_retry
from tools.stock_price import get_stock_price
from tools.recent_news import get_recent_news
from tools.company_fundamentals import get_company_fundamentals

# Initialize ISO-8601 UTC logging with request UUIDs
logger = setup_mcp_logging(level=logging.INFO)

def test_cache_hits():
    print("\n--- 1. Testing TTL Cache Hits ---")
    ticker = "MSFT"
    print(f"Calling get_stock_price('{ticker}') [Call 1 - Uncached]...")
    res1 = get_stock_price(ticker)
    print("Call 1 result cached status:", res1.get("_cached", False))

    print(f"Calling get_stock_price('{ticker}') [Call 2 - Within TTL]...")
    res2 = get_stock_price(ticker)
    print("Call 2 result cached status:", res2.get("_cached", False))
    assert res2.get("_cached") is True, "Second call should hit TTL cache"
    print("SUCCESS: TTL Cache hit verified!")

def test_idempotency():
    print("\n--- 2. Testing Idempotency Keys ---")
    cron_key = "cron-run-2026-07-22-001"
    print(f"Calling get_company_fundamentals('NVDA', idempotency_key='{cron_key}') [Call 1]...")
    res1 = get_company_fundamentals("NVDA", idempotency_key=cron_key)
    print("Call 1 idempotent status:", res1.get("_idempotent", False))

    print(f"Calling get_company_fundamentals('NVDA', idempotency_key='{cron_key}') [Call 2]...")
    res2 = get_company_fundamentals("NVDA", idempotency_key=cron_key)
    print("Call 2 idempotent status:", res2.get("_idempotent", False))
    assert res2.get("_idempotent") is True, "Second call with same idempotency_key should short-circuit"
    print("SUCCESS: Idempotency short-circuit verified!")

def test_circuit_breaker_trip_and_fallback():
    print("\n--- 3. Testing Circuit Breaker Trip & Fallback ---")
    breaker = get_circuit_breaker("yfinance", failure_threshold=3, recovery_timeout=10.0)

    # Force 3 failures to trip circuit breaker
    print("Simulating 3 consecutive upstream failures to trip yfinance circuit breaker...")
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()

    print("Current yfinance circuit breaker state:", breaker.state)
    assert breaker.state == "OPEN", "Circuit breaker should be OPEN after 3 failures"

    # Call tool while circuit breaker is OPEN
    print("Calling get_stock_price('MSFT') while circuit breaker is OPEN...")
    res = get_stock_price("MSFT")
    print("Degraded/Cached result returned:", res)
    assert res.get("_circuit_degraded") is True or res.get("degraded") is True, "Should return cached or degraded result"
    print("SUCCESS: Circuit breaker trip & fallback verified!")

    # Reset breaker state for clean exit
    breaker.record_success()

def test_retry_on_transient_failure():
    print("\n--- 4. Testing Exponential Retry with Jitter ---")
    attempts_counter = 0

    @with_retry(max_attempts=3, backoff_base=0.1, jitter=True)
    def flaky_api_call():
        nonlocal attempts_counter
        attempts_counter += 1
        print(f"Executing flaky_api_call() attempt #{attempts_counter}...")
        if attempts_counter < 3:
            raise ConnectionError(f"Simulated transient network glitch on attempt #{attempts_counter}")
        return {"status": "success", "attempts": attempts_counter}

    res = flaky_api_call()
    print("Flaky call final result:", res)
    assert res.get("status") == "success" and attempts_counter == 3, "Retry decorator should succeed on 3rd attempt"
    print("SUCCESS: Retry with jitter verified!")

if __name__ == "__main__":
    print("==========================================")
    print("RUNNING RELIABILITY SUITE WITH DETAILED LOGS & UUIDs")
    print("==========================================")
    test_cache_hits()
    test_idempotency()
    test_circuit_breaker_trip_and_fallback()
    test_retry_on_transient_failure()
    print("\n==========================================")
    print("ALL RELIABILITY TESTS PASSED SUCCESSFULLY!")
    print("==========================================")
