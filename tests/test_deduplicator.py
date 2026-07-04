from app.agents.deduplicator import dedupe_node
from app.models.schemas import SourceType


def _finding(title, url, confidence=0.5, facts=None):
    return {
        "title": title,
        "main_idea": title,
        "facts": facts or [],
        "statistics": [],
        "dates": [],
        "names": [],
        "links": [url],
        "source": SourceType.WEB.value,
        "url": url,
        "confidence": confidence,
    }


def test_exact_url_duplicates_are_merged_keeping_higher_confidence():
    state = {
        "extracted": [
            _finding("GPT-5 announced", "https://example.com/a", confidence=0.4, facts=["fact1"]),
            _finding("GPT-5 announced", "https://example.com/a", confidence=0.9, facts=["fact2"]),
        ]
    }
    result = dedupe_node(state)
    assert len(result["deduped"]) == 1
    merged = result["deduped"][0]
    assert merged["confidence"] == 0.9
    assert set(merged["facts"]) == {"fact1", "fact2"}


def test_near_duplicate_titles_from_different_urls_are_merged():
    state = {
        "extracted": [
            _finding("OpenAI releases GPT-5 model", "https://a.com/1"),
            _finding("OpenAI releases GPT-5 model today", "https://b.com/2"),
        ]
    }
    result = dedupe_node(state)
    assert len(result["deduped"]) == 1


def test_distinct_findings_are_kept_separate():
    state = {
        "extracted": [
            _finding("OpenAI releases GPT-5", "https://a.com/1"),
            _finding("Tesla reports Q3 earnings", "https://b.com/2"),
        ]
    }
    result = dedupe_node(state)
    assert len(result["deduped"]) == 2
