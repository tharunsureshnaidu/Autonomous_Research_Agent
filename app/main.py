"""FastAPI entrypoint: exposes the research pipeline and session memory over HTTP."""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.graph import get_graph
from app.models.database import get_db, init_db
from app.models.schemas import ResearchRequest, SessionRecord
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("database initialized")
    yield


app = FastAPI(
    title="Autonomous Research Agent",
    description="Multi-agent system that plans, searches, filters, and synthesizes research reports autonomously.",
    version="1.0.0",
    lifespan=lifespan,
)


def _initial_state(query: str) -> dict:
    return {"session_id": str(uuid.uuid4()), "query": query, "logs": []}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/research")
async def run_research(request: ResearchRequest) -> dict:
    """Run the full pipeline synchronously and return the final report."""
    graph = get_graph()
    final_state = await graph.ainvoke(_initial_state(request.query))
    return {
        "session_id": final_state["session_id"],
        "query": final_state["query"],
        "markdown": final_state["report_markdown"],
        "summary": final_state["summary"],
        "references": final_state["references"],
        "markdown_path": final_state["markdown_path"],
        "pdf_path": final_state["pdf_path"],
        "reasoning_log": final_state["logs"],
    }


@app.post("/api/research/stream")
async def stream_research(request: ResearchRequest) -> StreamingResponse:
    """Run the pipeline, streaming each agent's reasoning log line as it completes (SSE)."""
    graph = get_graph()

    async def event_stream():
        initial_state = _initial_state(request.query)
        # stream_mode="updates" only yields each node's own return payload, never
        # the original invocation input - so session_id has to be seeded here or
        # it stays null in the final "done" event.
        final_state: dict = dict(initial_state)
        async for update in graph.astream(initial_state, stream_mode="updates"):
            for node_name, payload in update.items():
                final_state.update(payload)
                for line in payload.get("logs", []):
                    yield f"event: log\ndata: {json.dumps({'node': node_name, 'message': line})}\n\n"
        yield f"event: done\ndata: {json.dumps({'session_id': final_state.get('session_id'), 'markdown': final_state.get('report_markdown')})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/history")
async def list_history(limit: int = Query(default=50, ge=1, le=200)) -> list[SessionRecord]:
    return get_db().list_sessions(limit=limit)


@app.get("/api/history/similar")
async def find_similar(query: str = Query(..., min_length=3)) -> list[SessionRecord]:
    """Find past research sessions similar enough to `query` to be reused instead of re-run."""
    return get_db().find_similar(query)


@app.get("/api/history/{session_id}")
async def get_session(session_id: str) -> dict:
    result = get_db().get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    record, markdown = result
    return {"record": record, "markdown": markdown}


@app.get("/api/history/{session_id}/report.md")
async def download_markdown(session_id: str) -> FileResponse:
    result = get_db().get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    record, _ = result
    return FileResponse(record.markdown_path, media_type="text/markdown", filename=f"{session_id}.md")


@app.get("/api/history/{session_id}/report.pdf")
async def download_pdf(session_id: str) -> FileResponse:
    result = get_db().get_session(session_id)
    if result is None or not result[0].pdf_path:
        raise HTTPException(status_code=404, detail="PDF not found for this session")
    record, _ = result
    return FileResponse(record.pdf_path, media_type="application/pdf", filename=f"{session_id}.pdf")
