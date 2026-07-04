"""Fetch a URL and extract its main readable text (strips nav/ads/boilerplate)."""
from __future__ import annotations

import httpx
import trafilatura
from tenacity import retry, stop_after_attempt, wait_exponential

from app.utils.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AutonomousResearchAgent/1.0)"}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
async def fetch_and_extract(url: str) -> str:
    """Download `url` and return its main body text, or "" on any failure."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.warning("scrape failed url=%s err=%s", url, exc)
        return ""

    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    return text.strip()
