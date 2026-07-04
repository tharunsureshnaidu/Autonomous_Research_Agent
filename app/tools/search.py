"""Search tool implementations, one per source type, behind a single async dispatch().

Each function is a thin, retried wrapper around a provider's API and returns
plain dicts (not RawResult) so this module has zero dependency on the agent
layer. A tiny TTL cache avoids re-hitting providers for repeated queries
within a session (bonus: "search caching").
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models.schemas import SourceType
from app.utils.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Wikipedia's API rejects requests without a descriptive User-Agent (returns 403);
# arXiv now redirects plain-http requests to https.
_HEADERS = {"User-Agent": "AutonomousResearchAgent/1.0 (research-assistant; contact@example.com)"}

_cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}


def _cache_get(source: str, query: str) -> list[dict[str, Any]] | None:
    key = (source, query.lower().strip())
    hit = _cache.get(key)
    if not hit:
        return None
    ts, results = hit
    if time.time() - ts > get_settings().search_cache_ttl_seconds:
        _cache.pop(key, None)
        return None
    return results


def _cache_set(source: str, query: str, results: list[dict[str, Any]]) -> None:
    _cache[(source, query.lower().strip())] = (time.time(), results)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
async def search_tavily(query: str, max_results: int) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.tavily_api_key:
        return []
    from tavily import AsyncTavilyClient

    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    resp = await client.search(query=query, max_results=max_results)
    return [
        {
            "url": r["url"],
            "title": r.get("title", ""),
            "snippet": r.get("content", ""),
            "published_date": r.get("published_date"),
        }
        for r in resp.get("results", [])
    ]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
async def search_web(query: str, max_results: int) -> list[dict[str, Any]]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return [
        {"url": r.get("href", ""), "title": r.get("title", ""), "snippet": r.get("body", ""), "published_date": None}
        for r in results
    ]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
async def search_news(query: str, max_results: int) -> list[dict[str, Any]]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.news(query, max_results=max_results))
    return [
        {
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "snippet": r.get("body", ""),
            "published_date": r.get("date"),
        }
        for r in results
    ]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
async def search_wikipedia(query: str, max_results: int) -> list[dict[str, Any]]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_HEADERS, follow_redirects=True) as client:
        resp = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": max_results,
            },
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search", [])
    return [
        {
            "url": f"https://en.wikipedia.org/wiki/{h['title'].replace(' ', '_')}",
            "title": h["title"],
            "snippet": _strip_html(h.get("snippet", "")),
            "published_date": None,
        }
        for h in hits
    ]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
async def search_arxiv(query: str, max_results: int) -> list[dict[str, Any]]:
    import xml.etree.ElementTree as ET

    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_HEADERS, follow_redirects=True) as client:
        resp = await client.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "start": 0, "max_results": max_results},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("atom:entry", ns):
        results.append(
            {
                "url": entry.findtext("atom:id", default="", namespaces=ns),
                "title": (entry.findtext("atom:title", default="", namespaces=ns) or "").strip(),
                "snippet": (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()[:500],
                "published_date": entry.findtext("atom:published", default=None, namespaces=ns),
            }
        )
    return results


def _strip_html(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", text)


_DISPATCH = {
    SourceType.TAVILY: search_tavily,
    SourceType.WEB: search_web,
    SourceType.NEWS: search_news,
    SourceType.WIKIPEDIA: search_wikipedia,
    SourceType.ARXIV: search_arxiv,
}


async def dispatch(source: SourceType, query: str, max_results: int | None = None) -> list[dict[str, Any]]:
    """Run the search for one (source, query) pair, using the cache when possible."""
    settings = get_settings()
    max_results = max_results or settings.max_search_results_per_source

    cached = _cache_get(source.value, query)
    if cached is not None:
        logger.info("cache hit: %s | %s", source.value, query)
        return cached

    fn = _DISPATCH.get(source)
    if fn is None:
        logger.warning("Unknown source type requested: %s", source)
        return []

    try:
        results = await fn(query, max_results)
    except Exception:
        logger.exception("search failed for source=%s query=%s", source.value, query)
        return []

    _cache_set(source.value, query, results)
    return results
