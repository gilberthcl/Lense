"""Web search — DDG HTML parsing + URL unwrapping (pure)."""
from app.services import web_search as ws

_SAMPLE = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fattack.mitre.org%2Ftechniques%2FT1110%2F&rut=x">
    Brute Force, Technique T1110
  </a>
  <a class="result__snippet" href="...">Adversaries may use brute force to gain access.</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/page">Example &amp; Co</a>
  <a class="result__snippet" href="...">A <b>snippet</b> &amp; more here.</a>
</div>
"""


def test_parse_extracts_title_url_snippet():
    out = ws.parse_results(_SAMPLE)
    assert len(out) == 2
    assert out[0]["title"] == "Brute Force, Technique T1110"
    assert out[0]["url"] == "https://attack.mitre.org/techniques/T1110/"   # unwrapped
    assert "brute force" in out[0]["snippet"].lower()


def test_parse_decodes_entities_and_strips_tags():
    out = ws.parse_results(_SAMPLE)
    assert out[1]["title"] == "Example & Co"
    assert out[1]["snippet"] == "A snippet & more here."   # tags stripped, entities decoded
    assert out[1]["url"] == "https://example.com/page"   # already-real url kept


def test_parse_respects_max_results_and_empty():
    assert ws.parse_results(_SAMPLE, max_results=1)[0]["title"].startswith("Brute")
    assert ws.parse_results("<html>no results</html>") == []
