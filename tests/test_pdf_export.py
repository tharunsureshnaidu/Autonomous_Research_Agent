import tempfile
from pathlib import Path

from app.tools.pdf_export import markdown_to_pdf
from app.utils.config import get_settings


def test_markdown_to_pdf_writes_a_nonempty_pdf_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(get_settings(), "reports_dir", tmp)
        markdown = "# Research Summary\n\n## Key Findings\n\n- point one\n- point two\n"
        path = markdown_to_pdf("session-123", "test query", markdown)

        pdf_path = Path(path)
        assert pdf_path.exists()
        assert pdf_path.read_bytes()[:4] == b"%PDF"
