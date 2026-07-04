import pytest

from app.tools.llm_client import _parse_json_loose


def test_parses_clean_json():
    assert _parse_json_loose('{"a": 1}') == {"a": 1}


def test_strips_markdown_code_fences():
    text = '```json\n{"a": 1, "b": [1, 2]}\n```'
    assert _parse_json_loose(text) == {"a": 1, "b": [1, 2]}


def test_extracts_json_object_surrounded_by_commentary():
    text = 'Sure, here is the result:\n{"a": 1}\nLet me know if you need anything else.'
    assert _parse_json_loose(text) == {"a": 1}


def test_raises_on_unparseable_text():
    with pytest.raises(Exception):
        _parse_json_loose("not json at all")
