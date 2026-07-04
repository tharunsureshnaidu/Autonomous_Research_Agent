"""Memory Storage: persists the completed session so it can be listed, fetched, or reused later."""
from __future__ import annotations

from app.agents.state import ResearchState
from app.models.database import get_db
from app.models.schemas import ResearchSummary, SessionRecord, SourceType
from app.utils.logger import get_logger

logger = get_logger(__name__)


def store_node(state: ResearchState) -> dict:
    summary = ResearchSummary.model_validate(state["summary"])
    sources = sorted({SourceType(t["source"]).value for t in state.get("search_tasks", [])})

    record = SessionRecord(
        session_id=state["session_id"],
        query=state["query"],
        timestamp=state["generated_at"],
        executive_summary=summary.executive_summary,
        sources=sources,
        markdown_path=state["markdown_path"],
        pdf_path=state.get("pdf_path"),
    )
    get_db().save_session(record, state["report_markdown"])
    logger.info("session %s persisted to memory", state["session_id"])
    return {"logs": [f"Memory: session {state['session_id']} saved"]}
