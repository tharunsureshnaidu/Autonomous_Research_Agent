"""Deduplication Agent: collapses duplicate URLs, duplicate facts, and near-identical findings.

Two passes, cheapest first:
1. Exact URL dedup (keep the highest-confidence copy).
2. Near-duplicate text dedup via difflib similarity on title+main_idea,
   merging their fact/statistic/date/name lists when they clearly describe
   the same thing - no LLM call needed for this, it's a mechanical merge.
"""
from __future__ import annotations

import difflib

from app.agents.state import ResearchState
from app.models.schemas import ExtractedFinding
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SIMILARITY_THRESHOLD = 0.82


def _dedupe_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _merge(a: ExtractedFinding, b: ExtractedFinding) -> ExtractedFinding:
    primary, secondary = (a, b) if a.confidence >= b.confidence else (b, a)
    return ExtractedFinding(
        title=primary.title,
        main_idea=primary.main_idea,
        facts=_dedupe_list(primary.facts + secondary.facts),
        statistics=_dedupe_list(primary.statistics + secondary.statistics),
        dates=_dedupe_list(primary.dates + secondary.dates),
        names=_dedupe_list(primary.names + secondary.names),
        links=_dedupe_list(primary.links + secondary.links),
        source=primary.source,
        url=primary.url,
        confidence=max(a.confidence, b.confidence),
    )


def dedupe_node(state: ResearchState) -> dict:
    findings = [ExtractedFinding.model_validate(f) for f in state.get("extracted", [])]

    by_url: dict[str, ExtractedFinding] = {}
    for f in findings:
        key = f.url.strip().rstrip("/")
        by_url[key] = _merge(by_url[key], f) if key in by_url else f
    url_deduped = list(by_url.values())

    merged: list[ExtractedFinding] = []
    for finding in url_deduped:
        signature = f"{finding.title} {finding.main_idea}".lower()
        match_idx = None
        for idx, existing in enumerate(merged):
            existing_signature = f"{existing.title} {existing.main_idea}".lower()
            if difflib.SequenceMatcher(None, signature, existing_signature).ratio() >= _SIMILARITY_THRESHOLD:
                match_idx = idx
                break
        if match_idx is None:
            merged.append(finding)
        else:
            merged[match_idx] = _merge(merged[match_idx], finding)

    logger.info("dedup: %d findings -> %d after URL dedup -> %d after near-duplicate merge", len(findings), len(url_deduped), len(merged))
    return {
        "deduped": [f.model_dump(mode="json") for f in merged],
        "logs": [f"Deduplicator: {len(findings)} -> {len(merged)} unique findings"],
    }
