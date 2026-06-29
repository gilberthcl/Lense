"""parse_json_response robustness — fences, prose, and reasoning preambles."""
import pytest

from app.services import ollama_client as ollama


def test_plain_json():
    assert ollama.parse_json_response('{"a": 1}') == {"a": 1}


def test_fenced_json():
    assert ollama.parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_reasoning_preamble_with_braces():
    # gpt-oss/CyberPal style: a 'thinking' preamble that itself contains braces,
    # then the real JSON. first-{/last-} would mis-span; the balanced scanner wins.
    raw = (
        "We need to output JSON. The set {a, b} matters here.\n"
        'Final answer: {"finding": {"title": "ROPC abuse"}, "why_missed": "subtle"}'
    )
    out = ollama.parse_json_response(raw)
    assert out["finding"]["title"] == "ROPC abuse"


def test_braces_inside_strings_are_ignored():
    raw = 'prose {"msg": "a } b { c", "ok": true} trailing'
    out = ollama.parse_json_response(raw)
    assert out["ok"] is True and out["msg"] == "a } b { c"


def test_unparseable_raises():
    with pytest.raises(ollama.OllamaError):
        ollama.parse_json_response("no json here at all")
