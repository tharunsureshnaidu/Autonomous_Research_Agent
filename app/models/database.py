"""SQLite-backed session memory: every completed research run is persisted here.

Uses stdlib sqlite3 rather than an ORM — the schema is one table and the
access patterns are simple insert/list/get, so SQLAlchemy would only add
indirection. Reuse/history search is done via difflib similarity over past
queries; a real embedding index (FAISS/Chroma) is a drop-in upgrade if
semantic recall on large history ever matters more than exact-ish phrasing.
"""
from __future__ import annotations

import difflib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.models.schemas import SessionRecord
from app.utils.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    executive_summary TEXT NOT NULL,
    sources TEXT NOT NULL,
    markdown_path TEXT NOT NULL,
    pdf_path TEXT,
    report_markdown TEXT NOT NULL
);
"""


class ResearchDB:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or get_settings().database_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save_session(self, record: SessionRecord, report_markdown: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions
                   (session_id, query, timestamp, executive_summary, sources, markdown_path, pdf_path, report_markdown)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.session_id,
                    record.query,
                    record.timestamp,
                    record.executive_summary,
                    json.dumps(record.sources),
                    record.markdown_path,
                    record.pdf_path,
                    report_markdown,
                ),
            )

    def list_sessions(self, limit: int = 50) -> list[SessionRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def get_session(self, session_id: str) -> tuple[SessionRecord, str] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return _row_to_record(row), row["report_markdown"]

    def find_similar(self, query: str, threshold: float = 0.6, limit: int = 5) -> list[SessionRecord]:
        """Return past sessions whose query closely resembles `query` (reuse previous research)."""
        candidates = self.list_sessions(limit=200)
        scored = [
            (difflib.SequenceMatcher(None, query.lower(), c.query.lower()).ratio(), c) for c in candidates
        ]
        scored = [(s, c) for s, c in scored if s >= threshold]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [c for _, c in scored[:limit]]


def _row_to_record(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        session_id=row["session_id"],
        query=row["query"],
        timestamp=row["timestamp"],
        executive_summary=row["executive_summary"],
        sources=json.loads(row["sources"]),
        markdown_path=row["markdown_path"],
        pdf_path=row["pdf_path"],
    )


_db: ResearchDB | None = None


def init_db() -> ResearchDB:
    """Eagerly create the SQLite file and schema. Called once at app startup
    so a missing/corrupt DB path fails fast instead of on a request thread."""
    global _db
    _db = ResearchDB()
    return _db


def get_db() -> ResearchDB:
    global _db
    if _db is None:
        _db = init_db()
    return _db
