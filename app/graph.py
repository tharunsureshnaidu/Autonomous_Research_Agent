"""Wires every agent into the LangGraph pipeline:

Planner -> Source Selector -> [parallel Search Workers] -> Extractor
        -> Deduplicator -> Relevance Scorer -> Summarizer
        -> Report Generator -> Memory Storage

The Search Workers step is a genuine parallel fan-out (via `Send`), one
branch per (source, query) task, joining back into the Extractor node.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.deduplicator import dedupe_node
from app.agents.extractor import extract_node
from app.agents.memory import store_node
from app.agents.planner import plan_node
from app.agents.relevance_scorer import score_node
from app.agents.report_generator import report_node
from app.agents.researcher import fan_out_search_tasks, search_worker_node
from app.agents.source_selector import select_sources_node
from app.agents.state import ResearchState
from app.agents.summarizer import summarize_node


def build_graph():
    graph = StateGraph(ResearchState)

    # Node ids are distinct from the state keys they write (e.g. "planner" vs
    # "plan") - LangGraph rejects a node name that collides with a state key.
    graph.add_node("planner", plan_node)
    graph.add_node("select_sources", select_sources_node)
    graph.add_node("search_worker", search_worker_node)
    graph.add_node("extract", extract_node)
    graph.add_node("dedupe", dedupe_node)
    graph.add_node("relevance_scorer", score_node)
    graph.add_node("summarizer", summarize_node)
    graph.add_node("report_generator", report_node)
    graph.add_node("memory_store", store_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "select_sources")
    graph.add_conditional_edges("select_sources", fan_out_search_tasks, ["search_worker"])
    graph.add_edge("search_worker", "extract")
    graph.add_edge("extract", "dedupe")
    graph.add_edge("dedupe", "relevance_scorer")
    graph.add_edge("relevance_scorer", "summarizer")
    graph.add_edge("summarizer", "report_generator")
    graph.add_edge("report_generator", "memory_store")
    graph.add_edge("memory_store", END)

    return graph.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
