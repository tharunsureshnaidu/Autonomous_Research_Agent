from unittest.mock import patch

from app.agents.relevance_scorer import score_node
from app.models.schemas import SourceType


def _finding(title="t", url="https://example.com", **overrides):
    base = dict(
        title=title, main_idea="m", facts=[], statistics=[], dates=[], names=[],
        links=[], source=SourceType.WEB.value, url=url, confidence=0.5,
    )
    base.update(overrides)
    return base


async def _fake_complete_json(judged_scores):
    async def fn(system, user, max_tokens=2000):
        return {"scores": judged_scores}

    return fn


async def test_score_node_returns_no_findings_when_input_empty():
    result = await score_node({"query": "q", "deduped": []})
    assert result["scored"] == []
    assert result["filtered"] == []


async def test_score_node_uses_llm_judged_scores_and_filters_by_threshold():
    findings = [_finding(title="high quality"), _finding(title="low quality")]
    judged = [
        {"relevance": 0.9, "credibility": 0.9, "freshness": 0.9, "completeness": 0.9},
        {"relevance": 0.1, "credibility": 0.1, "freshness": 0.1, "completeness": 0.1},
    ]
    with patch("app.tools.llm_client.LLMClient.complete_json", side_effect=await _fake_complete_json(judged)):
        result = await score_node({"query": "q", "deduped": findings})

    assert len(result["scored"]) == 2
    assert len(result["filtered"]) == 1
    assert result["filtered"][0]["finding"]["title"] == "high quality"


async def test_score_node_falls_back_to_neutral_scores_when_llm_call_fails():
    findings = [_finding()]
    with patch("app.tools.llm_client.LLMClient.complete_json", side_effect=RuntimeError("boom")):
        result = await score_node({"query": "q", "deduped": findings})

    assert len(result["scored"]) == 1
    scored = result["scored"][0]
    assert scored["relevance"] == scored["credibility"] == scored["freshness"] == scored["completeness"] == 0.5


async def test_score_node_falls_back_when_llm_returns_mismatched_score_count():
    findings = [_finding(), _finding(title="second")]
    with patch("app.tools.llm_client.LLMClient.complete_json", side_effect=await _fake_complete_json([{"relevance": 1.0, "credibility": 1.0, "freshness": 1.0, "completeness": 1.0}])):
        result = await score_node({"query": "q", "deduped": findings})

    assert len(result["scored"]) == 2
    assert all(s["relevance"] == 0.5 for s in result["scored"])
