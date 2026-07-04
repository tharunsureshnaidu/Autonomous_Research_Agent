"""Relevance Scoring Agent: judges every finding on relevance, credibility, freshness, completeness.

All four dimensions are judged by the LLM in a single batched call per run -
there is no fixed domain allowlist or date-arithmetic formula deciding
credibility/freshness here. The model reasons about domain reputation,
apparent recency, and information density itself, the same way a human
researcher would skim a source and judge it. A neutral-score fallback exists
only for the LLM-unavailable error path, never as the primary decision path.
"""
from __future__ import annotations

from app.agents.state import ResearchState
from app.models.schemas import ExtractedFinding, ScoredFinding
from app.tools.llm_client import get_llm_client
from app.utils.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM = """You are the Relevance & Quality Scoring Agent of an autonomous research system.
You are given a research query and a numbered list of findings extracted from various
sources. For EACH finding, reason about and score four independent dimensions from 0.0 to 1.0:

- "relevance": how directly this finding helps answer the research query.
- "credibility": how authoritative/trustworthy the source appears, based on the URL's
  domain and the nature of the content (e.g. a government/academic/major-outlet domain
  or a well-established encyclopedia/journal is more credible than an anonymous blog or
  forum post) - use your own knowledge of the web to judge this, there is no fixed list.
- "freshness": how recent the information appears to be, based on any dates mentioned
  and the nature of the topic (rapidly-evolving topics need more recent sources than
  historical/stable ones).
- "completeness": how substantive and informative this finding is (rich in concrete
  facts/statistics/names) versus vague or thin.

Respond as JSON matching exactly:
{"scores": [{"relevance": 0.0, "credibility": 0.0, "freshness": 0.0, "completeness": 0.0}, ...]}
with one object per finding, in order.
"""

_DIMENSIONS = ("relevance", "credibility", "freshness", "completeness")


def _format_finding(f: ExtractedFinding, idx: int) -> str:
    parts = [f"{idx}. {f.title} - {f.main_idea} (url: {f.url})"]
    if f.facts:
        parts.append(f"   facts: {'; '.join(f.facts)}")
    if f.statistics:
        parts.append(f"   statistics: {'; '.join(f.statistics)}")
    if f.dates:
        parts.append(f"   dates mentioned: {'; '.join(f.dates)}")
    return "\n".join(parts)


async def score_node(state: ResearchState) -> dict:
    findings = [ExtractedFinding.model_validate(f) for f in state.get("deduped", [])]
    if not findings:
        return {"scored": [], "filtered": [], "logs": ["Relevance Scorer: no findings to score"]}

    client = get_llm_client()
    listing = "\n".join(_format_finding(f, i + 1) for i, f in enumerate(findings))
    try:
        raw = await client.complete_json(_SYSTEM, f"Query: {state['query']}\n\nFindings:\n{listing}", max_tokens=2500)
        judged = raw.get("scores", [])
        if len(judged) != len(findings):
            raise ValueError("score count mismatch")
        dimension_scores = [{k: max(0.0, min(1.0, float(s.get(k, 0.5)))) for k in _DIMENSIONS} for s in judged]
    except Exception:
        logger.exception("relevance/quality scoring LLM call failed, falling back to neutral scores")
        dimension_scores = [{k: 0.5 for k in _DIMENSIONS} for _ in findings]

    scored = [ScoredFinding(finding=f, **dimension_scores[i]) for i, f in enumerate(findings)]

    threshold = get_settings().relevance_score_threshold
    filtered = sorted((s for s in scored if s.total_score >= threshold), key=lambda s: s.total_score, reverse=True)

    logger.info("scored %d findings, %d passed threshold %.2f", len(scored), len(filtered), threshold)
    return {
        "scored": [s.model_dump(mode="json") for s in scored],
        "filtered": [s.model_dump(mode="json") for s in filtered],
        "logs": [f"Relevance Scorer: {len(filtered)}/{len(scored)} findings kept (threshold {threshold})"],
    }
