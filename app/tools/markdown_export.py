"""Persist a generated report as a Markdown file."""
from __future__ import annotations

from pathlib import Path

from app.utils.config import get_settings


def save_markdown(session_id: str, content: str) -> str:
    """Write `content` to <reports_dir>/<session_id>.md and return the path."""
    reports_dir = Path(get_settings().reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{session_id}.md"
    path.write_text(content, encoding="utf-8")
    return str(path)
