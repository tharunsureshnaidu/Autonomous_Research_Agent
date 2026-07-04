"""API-level tests against the full FastAPI app, with the LLM/search layers mocked
so these run without network access or API keys.
"""
import json
import os
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test")

from fastapi.testclient import TestClient

from app.main import app

PLAN_JSON = {
    "research_goal": "Explain X",
    "information_needed": [{"topic": "what is X", "reasoning": "core ask", "priority": 1}],
    "candidate_sources": ["wikipedia"],
    "expected_output": "A short explanation of X",
}
SOURCE_SELECTION_JSON = {
    "tasks": [{"source": "wikipedia", "query": "X", "information_need": "what is X", "priority": 1}]
}
EXTRACTION_JSON = {
    "title": "X overview",
    "main_idea": "X is a well-documented concept with several defining traits.",
    "facts": ["X was first described in the literature"],
    "statistics": [],
    "dates": [],
    "names": [],
    "confidence": 0.8,
}
RELEVANCE_JSON = {"scores": [{"relevance": 0.9, "credibility": 0.9, "freshness": 0.9, "completeness": 0.9}]}
SUMMARY_JSON = {
    "executive_summary": "X is a well-documented concept.",
    "key_findings": ["X was first described in the literature"],
    "detailed_analysis": "X has several defining traits documented across sources.",
    "important_statistics": [],
    "risks_and_limitations": [],
    "actionable_insights": ["Learn more about X"],
}


def _llm_side_effects():
    sequence = [PLAN_JSON, SOURCE_SELECTION_JSON, EXTRACTION_JSON, RELEVANCE_JSON, SUMMARY_JSON]

    async def fake_complete_json(system, user, max_tokens=2000):
        return sequence.pop(0)

    return fake_complete_json


async def _fake_dispatch(source, query, max_results=None):
    return [{"url": "https://en.wikipedia.org/wiki/X", "title": "X", "snippet": "X is a concept.", "published_date": None}]


async def _fake_fetch(url):
    return "X is a well-documented concept with a long history and several defining characteristics worth noting."


def _patched():
    return (
        patch("app.tools.llm_client.LLMClient.complete_json", side_effect=_llm_side_effects()),
        patch("app.tools.search.dispatch", side_effect=_fake_dispatch),
        patch("app.tools.web_scraper.fetch_and_extract", side_effect=_fake_fetch),
    )


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_research_query_validation_rejects_short_query():
    with TestClient(app) as client:
        r = client.post("/api/research", json={"query": "ab"})
        assert r.status_code == 422


def test_history_lookup_404s_for_unknown_session():
    with TestClient(app) as client:
        r = client.get("/api/history/does-not-exist")
        assert r.status_code == 404


def test_research_endpoint_runs_pipeline_and_persists_history():
    p1, p2, p3 = _patched()
    with p1, p2, p3, TestClient(app) as client:
        r = client.post("/api/research", json={"query": "What is X?"})
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"]
        assert "# Research Summary" in data["markdown"]
        assert data["references"] == ["https://en.wikipedia.org/wiki/X"]

        history = client.get("/api/history").json()
        assert any(s["session_id"] == data["session_id"] for s in history)

        md = client.get(f"/api/history/{data['session_id']}/report.md")
        assert md.status_code == 200
        assert b"Research Summary" in md.content

        pdf = client.get(f"/api/history/{data['session_id']}/report.pdf")
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"

        os.remove(data["markdown_path"])
        os.remove(data["pdf_path"])


def test_stream_endpoint_done_event_carries_session_id():
    p1, p2, p3 = _patched()
    with p1, p2, p3, TestClient(app) as client:
        with client.stream("POST", "/api/research/stream", json={"query": "What is X?"}) as r:
            assert r.status_code == 200
            buf = "".join(r.iter_text())
        events = [e for e in buf.split("\n\n") if e.strip()]

        assert any(e.startswith("event: log") for e in events)
        done_events = [e for e in events if e.startswith("event: done")]
        assert len(done_events) == 1

        data_line = next(line for line in done_events[0].splitlines() if line.startswith("data:"))
        payload = json.loads(data_line[len("data: "):])
        assert payload["session_id"], "regression: done event must carry the session_id, not null"
        assert "# Research Summary" in payload["markdown"]
