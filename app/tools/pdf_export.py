"""Render the Markdown report into a professionally formatted PDF.

Uses fpdf2 (pure Python, no system dependencies like wkhtmltopdf/cairo) with
a small hand-rolled Markdown renderer covering the subset our report
template actually produces: #/##/### headings, bullet lists, and paragraphs.
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from app.utils.config import get_settings

_MARGIN = 18
_NAVY = (30, 41, 59)
_SLATE = (71, 85, 105)
_ACCENT = (37, 99, 235)


class _ReportPDF(FPDF):
    def __init__(self, title: str) -> None:
        super().__init__(format="A4")
        self._title = title
        self.set_auto_page_break(auto=True, margin=_MARGIN)
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_SLATE)
        self.cell(0, 8, self._title[:90], align="L")
        self.ln(10)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_SLATE)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def markdown_to_pdf(session_id: str, query: str, markdown: str) -> str:
    """Convert `markdown` into a styled PDF and return the written file path."""
    pdf = _ReportPDF(title=query)
    pdf.add_page()

    # Cover block
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*_NAVY)
    pdf.multi_cell(0, 12, "Autonomous Research Report")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(*_ACCENT)
    pdf.multi_cell(0, 8, _safe(query))
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.8)
    pdf.line(_MARGIN, pdf.get_y() + 3, 210 - _MARGIN, pdf.get_y() + 3)
    pdf.ln(10)

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            pdf.ln(3)
            continue
        _render_line(pdf, line)

    settings = get_settings()
    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{session_id}.pdf"
    pdf.output(str(path))
    return str(path)


def _safe(text: str) -> str:
    """The built-in Helvetica font only supports latin-1; LLM output routinely
    contains smart quotes/em-dashes/etc., so replace anything outside that
    range rather than letting fpdf2 raise mid-render."""
    return text.encode("latin-1", "replace").decode("latin-1")


def _render_line(pdf: _ReportPDF, line: str) -> None:
    pdf.set_x(_MARGIN)
    if line.startswith("### "):
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*_NAVY)
        pdf.ln(2)
        pdf.multi_cell(0, 7, _safe(line[4:]))
    elif line.startswith("## "):
        pdf.set_font("Helvetica", "B", 15)
        pdf.set_text_color(*_ACCENT)
        pdf.ln(3)
        pdf.multi_cell(0, 8, _safe(line[3:]))
    elif line.startswith("# "):
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(*_NAVY)
        pdf.ln(4)
        pdf.multi_cell(0, 9, _safe(line[2:]))
    elif line.startswith(("- ", "* ")):
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(*_SLATE)
        pdf.set_x(_MARGIN + 4)
        pdf.multi_cell(0, 6, _safe(f"- {line[2:]}"))
    else:
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(0, 6, _safe(line.lstrip("#").strip()))
