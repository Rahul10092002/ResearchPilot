import logging
import sys
from mcp.server.fastmcp import FastMCP

from tools.company_fundamentals import get_company_fundamentals as _get_company_fundamentals
from tools.recent_news import get_recent_news as _get_recent_news
from tools.stock_price import get_stock_price as _get_stock_price

# Configure logging to stderr to keep stdout clean for stdio MCP protocol transport
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_server")

# Initialize FastMCP Server
mcp = FastMCP("ResearchPilot MCP Server")


@mcp.tool()
def get_stock_price(ticker: str) -> dict:
    """Fetch the latest real-time or daily closing stock price for a company ticker.

    Args:
        ticker: The stock ticker symbol (e.g. 'AAPL', 'MSFT', 'NVDA', 'TSLA').

    Returns:
        Structured JSON dictionary containing ticker, price (float), currency (str),
        and ISO-8601 UTC timestamp, or an error payload if price lookup fails.
    """
    return _get_stock_price(ticker)


@mcp.tool()
def get_recent_news(topic: str, max_results: int = 5) -> dict:
    """Fetch recent news articles for a specific stock ticker or general research topic.

    Args:
        topic: Stock ticker symbol (e.g. 'AAPL') or search query (e.g. 'artificial intelligence regulation').
        max_results: Maximum number of news articles to return (default 5).

    Returns:
        Structured JSON dictionary containing query topic and a list of articles,
        where each article has headline, source, published_at, and url.
    """
    return _get_recent_news(topic, max_results=max_results)


@mcp.tool()
def get_company_fundamentals(ticker: str) -> dict:
    """Fetch key financial fundamental metrics and ratios for a company ticker.

    Args:
        ticker: The stock ticker symbol (e.g. 'AAPL', 'GOOGL', 'AMZN').

    Returns:
        Structured JSON dictionary with P/E ratio, Forward P/E, Market Cap, EPS,
        Revenue, Profit Margins, Dividend Yield, and 52-week High/Low ranges.
    """
    return _get_company_fundamentals(ticker)


# Expose ASGI app for Uvicorn HTTP transport (e.g., `uvicorn server:app --reload`)
app = mcp.sse_app()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ResearchPilot MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio" if not sys.stdin.isatty() else "sse",
        help="Transport protocol: 'stdio' for MCP client pipes, 'sse' for HTTP/SSE server",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        logger.info("Starting ResearchPilot MCP Server in SSE mode (HTTP)...")
        mcp.run(transport="sse")
    else:
        logger.info("Starting ResearchPilot MCP Server in stdio mode...")
        mcp.run(transport="stdio")
