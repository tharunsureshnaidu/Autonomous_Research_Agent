from app.agents.report_generator import render_markdown
from app.models.schemas import ResearchSummary


def test_render_markdown_includes_all_required_sections():
    summary = ResearchSummary(
        executive_summary="Overview text.",
        key_findings=["finding one", "finding two"],
        detailed_analysis="Paragraph of analysis.",
        important_statistics=["50% growth"],
        risks_and_limitations=["limited sample size"],
        actionable_insights=["do X next"],
    )
    markdown = render_markdown("test query", summary, ["https://a.com", "https://b.com"], "2026-01-01T00:00:00Z")

    for heading in [
        "# Research Summary",
        "## Executive Summary",
        "## Key Findings",
        "## Detailed Analysis",
        "## Important Statistics",
        "## Risks / Limitations",
        "## Actionable Insights",
        "## References",
    ]:
        assert heading in markdown

    assert "finding one" in markdown
    assert "https://a.com" in markdown


def test_render_markdown_handles_empty_references_gracefully():
    summary = ResearchSummary(
        executive_summary="No results.", key_findings=[], detailed_analysis="Nothing found.",
        important_statistics=[], risks_and_limitations=[], actionable_insights=[],
    )
    markdown = render_markdown("empty query", summary, [], "2026-01-01T00:00:00Z")
    assert "No sources met the relevance/credibility threshold." in markdown
