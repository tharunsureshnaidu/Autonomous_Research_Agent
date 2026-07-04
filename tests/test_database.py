import tempfile
from pathlib import Path

from app.models.database import ResearchDB
from app.models.schemas import SessionRecord


def _record(session_id, query, timestamp="2026-01-01T00:00:00+00:00"):
    return SessionRecord(
        session_id=session_id,
        query=query,
        timestamp=timestamp,
        executive_summary="summary",
        sources=["web"],
        markdown_path="/tmp/x.md",
        pdf_path=None,
    )


def test_save_and_get_session_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db = ResearchDB(db_path=str(Path(tmp) / "test.sqlite3"))
        db.save_session(_record("s1", "What is quantum computing?"), "# report body")

        result = db.get_session("s1")
        assert result is not None
        record, markdown = result
        assert record.query == "What is quantum computing?"
        assert markdown == "# report body"


def test_get_session_returns_none_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        db = ResearchDB(db_path=str(Path(tmp) / "test.sqlite3"))
        assert db.get_session("does-not-exist") is None


def test_list_sessions_orders_most_recent_first():
    with tempfile.TemporaryDirectory() as tmp:
        db = ResearchDB(db_path=str(Path(tmp) / "test.sqlite3"))
        db.save_session(_record("s1", "first query", timestamp="2026-01-01T00:00:00+00:00"), "body")
        db.save_session(_record("s2", "second query", timestamp="2026-01-02T00:00:00+00:00"), "body")

        sessions = db.list_sessions()
        assert [s.session_id for s in sessions] == ["s2", "s1"]


def test_find_similar_matches_close_queries_only():
    with tempfile.TemporaryDirectory() as tmp:
        db = ResearchDB(db_path=str(Path(tmp) / "test.sqlite3"))
        db.save_session(_record("s1", "latest advances in large language models"), "body")
        db.save_session(_record("s2", "best pizza recipes"), "body")

        matches = db.find_similar("recent advances in large language models")
        assert [m.session_id for m in matches] == ["s1"]
