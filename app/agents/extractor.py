"""Extraction Agent: turns raw scraped/snippet text into structured findings.

Runs one LLM extraction call per raw result, bounded by a semaphore so a
large fan-in doesn't blow through rate limits, and skips results with no
usable text instead of wasting a call on them.
"""
from __future__ import annotations

import asyncio

from app.agents.state import ResearchState
from app.models.schemas import ExtractedFinding, RawResult
from app.tools.llm_client import get_llm_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

_CONCURRENCY = 3  # conservative default - free-tier LLM keys (e.g. Mistral) rate-limit hard above this
_MIN_CONTENT_CHARS = 40

_SYSTEM = """You are the Extraction Agent of an autonomous research system.
Given the text of one source, extract only what is actually present - never invent facts.

Respond as JSON matching exactly:
{
  "title": "...",
  "main_idea": "one or two sentence summary of this source's core point",
  "facts": ["..."],
  "statistics": ["any numbers/percentages/counts mentioned, with context"],
  "dates": ["any dates or time references mentioned"],
  "names": ["people, organizations, or products named"],
  "confidence": 0.0-1.0 (how reliable/clear this source's information is)
}
If the text is too thin, sparse, or off-topic to extract meaningfully, set confidence below 0.3.
"""


async def extract_node(state: ResearchState) -> dict:
    raw_results = [RawResult.model_validate(r) for r in state.get("raw_results", [])]
    query = state["query"]
    client = get_llm_client()
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _extract_one(raw: RawResult) -> ExtractedFinding | None:
        text = (raw.content or raw.snippet or "").strip()
        if len(text) < _MIN_CONTENT_CHARS:
            return None
        async with semaphore:
            try:
                data = await client.complete_json(
                    _SYSTEM,
                    f"Research query context: {query}\n\nSource title: {raw.title}\nSource URL: {raw.url}\n\nSource text:\n{text[:6000]}",
                )
                return ExtractedFinding(
                    title=data.get("title") or raw.title,
                    main_idea=data.get("main_idea", ""),
                    facts=data.get("facts", []),
                    statistics=data.get("statistics", []),
                    dates=data.get("dates", []),
                    names=data.get("names", []),
                    links=[raw.url],
                    source=raw.source,
                    url=raw.url,
                    confidence=float(data.get("confidence", 0.5)),
                )
            except Exception:
                logger.exception("extraction failed for url=%s", raw.url)
                return None

    results = await asyncio.gather(*(_extract_one(r) for r in raw_results))
    findings = [f for f in results if f is not None]

    logger.info("extracted %d/%d usable findings", len(findings), len(raw_results))
    return {
        "extracted": [f.model_dump(mode="json") for f in findings],
        "logs": [f"Extractor: {len(findings)} structured findings from {len(raw_results)} raw results"],
    }
