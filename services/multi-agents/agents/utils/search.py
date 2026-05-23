import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


async def web_search(queries: list[str], max_results: int = 5) -> list[dict]:
    """Run queries concurrently via Tavily. Returns list of {title, url, content} dicts.
    Falls back to empty list if Tavily is unavailable."""
    if not _TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY not set, skipping web search")
        return []

    try:
        from tavily import AsyncTavilyClient
        client = AsyncTavilyClient(api_key=_TAVILY_API_KEY)

        async def _search(q: str) -> list[dict]:
            try:
                resp = await client.search(q, max_results=max_results, include_raw_content=False)
                return [
                    {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
                    for r in resp.get("results", [])
                ]
            except Exception as e:
                logger.warning("Tavily search failed for %r: %s", q, e)
                return []

        results = await asyncio.gather(*[_search(q) for q in queries])
        return [item for sublist in results for item in sublist]
    except ImportError:
        logger.warning("tavily-python not installed, skipping web search")
        return []
