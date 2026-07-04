"""Summarization Agent: synthesizes the filtered, ranked findings into a coherent narrative."""
from __future__ import annotations

from app.agents.state import ResearchState
from app.models.schemas import ResearchSummary, ScoredFinding
from app.tools.llm_client import get_llm_client
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM = """You are the Summarization Agent of an autonomous research system.
You are given the user's research query and a ranked list of vetted findings
(already deduplicated and filtered for relevance/credibility). Synthesize them
into a professional research summary. Do not invent information beyond what's
given; where findings conflict, note the disagreement rather than picking one.

Respond as JSON matching exactly:
{
  "executive_summary": "3-5 sentence overview answering the research query directly",
  "key_findings": ["...", "..."],
  "detailed_analysis": "several paragraphs synthesizing the findings, written in prose",
  "important_statistics": ["..."],
  "risks_and_limitations": ["gaps, caveats, or conflicting information in the research"],
  "actionable_insights": ["concrete recommendations or next steps"]
}
"""


def _fallback_summary(filtered: list[ScoredFinding]) -> ResearchSummary:
    """Mechanically assembled summary used when the LLM call fails (e.g. rate limit).

    The pipeline already spent real time and money gathering `filtered` - losing
    that work because the last LLM call in the chain hit a 429 would be far worse
    than handing back an unpolished but honest summary of what was found.
    """
    stats = [stat for s in filtered for stat in s.finding.statistics]
    return ResearchSummary(
        executive_summary=(
            "Automated synthesis was unavailable (LLM call failed), so this summary lists "
            "the raw vetted findings directly."
        ),
        key_findings=[s.finding.main_idea for s in filtered if s.finding.main_idea][:10],
        detailed_analysis="\n\n".join(
            f"{s.finding.title}: {s.finding.main_idea}" for s in filtered if s.finding.main_idea
        ),
        important_statistics=stats[:10],
        risks_and_limitations=["Summary synthesis step failed; findings below are unsynthesized."],
        actionable_insights=["Retry the request once the LLM provider is available for full synthesis."],
    )


def _format_finding(scored: ScoredFinding, idx: int) -> str:
    f = scored.finding
    parts = [
        f"[{idx}] {f.title} (source: {f.source.value}, score: {scored.total_score:.2f}, url: {f.url})",
        f"  Main idea: {f.main_idea}",
    ]
    if f.facts:
        parts.append(f"  Facts: {'; '.join(f.facts)}")
    if f.statistics:
        parts.append(f"  Statistics: {'; '.join(f.statistics)}")
    if f.dates:
        parts.append(f"  Dates: {'; '.join(f.dates)}")
    return "\n".join(parts)


async def summarize_node(state: ResearchState) -> dict:
    filtered = [ScoredFinding.model_validate(s) for s in state.get("filtered", [])]
    client = get_llm_client()

    if not filtered:
        summary = ResearchSummary(
            executive_summary="No sufficiently relevant or credible information was found for this query.",
            key_findings=[],
            detailed_analysis="The search and filtering pipeline did not surface findings that met the relevance/credibility threshold.",
            important_statistics=[],
            risks_and_limitations=["Insufficient source coverage for this query."],
            actionable_insights=["Consider rephrasing the query or broadening the source types."],
        )
    else:
        listing = "\n\n".join(_format_finding(s, i + 1) for i, s in enumerate(filtered))
        try:
            raw = await client.complete_json(
                _SYSTEM, f"Research query: {state['query']}\n\nVetted findings:\n{listing}", max_tokens=4500
            )
            summary = ResearchSummary.model_validate(raw)
        except Exception:
            logger.exception("summary synthesis LLM call failed, falling back to raw findings listing")
            summary = _fallback_summary(filtered)

    references = sorted({s.finding.url for s in filtered})
    logger.info("summary generated with %d key findings, %d references", len(summary.key_findings), len(references))
    return {
        "summary": summary.model_dump(mode="json"),
        "references": references,
        "logs": [f"Summarizer: synthesized {len(filtered)} findings into report summary"],
    }
