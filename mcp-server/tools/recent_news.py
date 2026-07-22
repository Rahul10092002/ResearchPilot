from datetime import datetime, timezone
import os
import re
import logging
from typing import Any, Dict, List
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _is_probable_ticker(topic: str) -> bool:
    """Check if the string looks like a standard stock ticker symbol."""
    clean = topic.strip().upper()
    return bool(re.match(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$", clean))


def _format_yf_news_item(item: dict) -> Dict[str, str]:
    """Extract and normalize yfinance news article items across different yfinance API structures."""
    content = item.get("content", item)
    title = content.get("title") or item.get("title", "")
    publisher = (
        content.get("provider", {}).get("displayName")
        if isinstance(content.get("provider"), dict)
        else (content.get("publisher") or item.get("publisher") or "yfinance")
    )
    url = (
        content.get("canonicalUrl", {}).get("url")
        if isinstance(content.get("canonicalUrl"), dict)
        else (content.get("link") or item.get("link") or "")
    )
    pub_time = (
        content.get("pubDate")
        or item.get("providerPublishTime")
        or datetime.now(timezone.utc).isoformat()
    )

    if isinstance(pub_time, (int, float)):
        pub_time = datetime.fromtimestamp(pub_time, tz=timezone.utc).isoformat()

    return {
        "headline": str(title).strip(),
        "source": str(publisher).strip(),
        "published_at": str(pub_time),
        "url": str(url).strip(),
    }


def get_recent_news(topic: str, max_results: int = 5) -> Dict[str, Any]:
    """Fetch recent news for a stock ticker symbol or general search topic.

    Tries yfinance news first if topic appears to be a ticker.
    Falls back to Tavily news search if available for generic queries or empty yfinance results.
    Returns structured JSON with articles list.
    """
    clean_topic = topic.strip()
    if not clean_topic:
        return {"topic": topic, "articles": [], "error": "Topic cannot be empty"}

    articles: List[Dict[str, str]] = []

    # 1. Attempt yfinance news if topic is ticker-like
    if _is_probable_ticker(clean_topic):
        try:
            t = yf.Ticker(clean_topic.upper())
            yf_news = getattr(t, "news", None)
            if yf_news and isinstance(yf_news, list):
                for item in yf_news[:max_results]:
                    formatted = _format_yf_news_item(item)
                    if formatted["headline"]:
                        articles.append(formatted)
        except Exception as e:
            logger.debug(f"yfinance news lookup failed for {clean_topic}: {e}")

    # 2. Fallback to Tavily if articles are empty or topic is general
    if not articles:
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key and tavily_key != "your_tavily_key_here":
            try:
                from tavily import TavilyClient

                tavily = TavilyClient(api_key=tavily_key)
                search_res = tavily.search(query=clean_topic, max_results=max_results)
                results = search_res.get("results", [])
                for item in results:
                    articles.append(
                        {
                            "headline": item.get("title", ""),
                            "source": item.get("domain") or "Tavily",
                            "published_at": item.get("published_date")
                            or datetime.now(timezone.utc).isoformat(),
                            "url": item.get("url", ""),
                        }
                    )
            except Exception as e:
                logger.debug(f"Tavily search failed for {clean_topic}: {e}")

    # 3. Secondary Fallback: yfinance Search for general queries if Tavily is unavailable
    if not articles and not _is_probable_ticker(clean_topic):
        try:
            search_obj = yf.Search(clean_topic, max_results=max_results)
            news_items = getattr(search_obj, "news", [])
            for item in news_items[:max_results]:
                formatted = _format_yf_news_item(item)
                if formatted["headline"]:
                    articles.append(formatted)
        except Exception as e:
            logger.debug(f"yfinance Search news failed for {clean_topic}: {e}")

    return {
        "topic": clean_topic,
        "articles": articles[:max_results],
        "count": len(articles[:max_results]),
    }
