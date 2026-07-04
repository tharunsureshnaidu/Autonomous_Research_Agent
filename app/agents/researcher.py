"""Parallel Search Workers.

Each search task selected upstream becomes its own LangGraph branch (fanned
out with `langgraph.types.Send` in app/graph.py), so different sources are
queried genuinely concurrently by the graph executor - not just via
asyncio.gather inside one node. Within a single branch, the worker also
fetches full page content for its top results concurrently.
"""
from __future__ import annotations

import asyncio

from langgraph.types import Send

from app.agents.state import ResearchState
from app.models.schemas import RawResult, SearchTask, SourceType
from app.tools import search as search_tool
from app.tools.web_scraper import fetch_and_extract
from app.utils.logger import get_logger

logger = get_logger(__name__)


def fan_out_search_tasks(state: ResearchState) -> list[Send]:
    """Conditional-edge function: turn each search task into its own worker branch."""
    tasks = state.get("search_tasks", [])
    return [Send("search_worker", {**state, "current_task": task}) for task in tasks]


async def search_worker_node(state: ResearchState) -> dict:
    task = SearchTask.model_validate(state["current_task"])
    logger.info("worker running: source=%s query=%r", task.source.value, task.query)

    hits = await search_tool.dispatch(task.source, task.query)

    async def _with_content(hit: dict) -> RawResult:
        content = ""
        if hit.get("url"):
            content = await fetch_and_extract(hit["url"])
        return RawResult(
            source=task.source,
            url=hit.get("url", ""),
            title=hit.get("title", ""),
            snippet=hit.get("snippet", ""),
            content=content or hit.get("snippet", ""),
            published_date=hit.get("published_date"),
        )

    enriched = await asyncio.gather(*(_with_content(h) for h in hits if h.get("url")))

    return {
        "raw_results": [r.model_dump(mode="json") for r in enriched],
        "logs": [f"Researcher[{task.source.value}]: '{task.query}' -> {len(enriched)} results"],
    }
