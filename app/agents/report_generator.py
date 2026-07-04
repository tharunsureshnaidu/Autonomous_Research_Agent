"""Report Generator: assembles the final Markdown report and exports it to disk."""
from __future__ import annotations

from datetime import datetime, timezone

from app.agents.state import ResearchState
from app.models.schemas import ResearchSummary
from app.tools.markdown_export import save_markdown
from app.tools.pdf_export import markdown_to_pdf
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None identified."


def render_markdown(query: str, summary: ResearchSummary, references: list[str], generated_at: str) -> str:
    return f"""# Research Summary

**Query:** {query}
**Generated:** {generated_at}

## Executive Summary

{summary.executive_summary}

## Key Findings

{_bullets(summary.key_findings)}

## Detailed Analysis

{summary.detailed_analysis}

## Important Statistics

{_bullets(summary.important_statistics)}

## Risks / Limitations

{_bullets(summary.risks_and_limitations)}

## Actionable Insights

{_bullets(summary.actionable_insights)}

## References

{_bullets(references) if references else "- No sources met the relevance/credibility threshold."}
"""


def report_node(state: ResearchState) -> dict:
    summary = ResearchSummary.model_validate(state["summary"])
    references = state.get("references", [])
    generated_at = datetime.now(timezone.utc).isoformat()

    markdown = render_markdown(state["query"], summary, references, generated_at)

    session_id = state["session_id"]
    markdown_path = save_markdown(session_id, markdown)
    pdf_path = markdown_to_pdf(session_id, state["query"], markdown)

    logger.info("report generated: md=%s pdf=%s", markdown_path, pdf_path)
    return {
        "report_markdown": markdown,
        "logs": [f"Report Generator: exported {markdown_path} and {pdf_path}"],
        "markdown_path": markdown_path,
        "pdf_path": pdf_path,
        "generated_at": generated_at,
    }
