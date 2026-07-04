"""The shared state threaded through every LangGraph node.

Kept as a TypedDict (LangGraph's native state shape) with plain
dict/list payloads produced by validating against the Pydantic models in
app.models.schemas at each node boundary — that gives us runtime validation
without forcing LangGraph to reconcile Pydantic model merges across
parallel branches.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ResearchState(TypedDict, total=False):
    session_id: str
    query: str

    plan: dict[str, Any]
    search_tasks: list[dict[str, Any]]

    # Parallel search workers each append here; `operator.add` merges branches.
    raw_results: Annotated[list[dict[str, Any]], operator.add]
    extracted: Annotated[list[dict[str, Any]], operator.add]

    deduped: list[dict[str, Any]]
    scored: list[dict[str, Any]]
    filtered: list[dict[str, Any]]

    summary: dict[str, Any]
    report_markdown: str
    references: list[str]
    markdown_path: str
    pdf_path: str
    generated_at: str

    logs: Annotated[list[str], operator.add]
