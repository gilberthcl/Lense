"""Model-fit guidance — pure heuristics, no Ollama."""
from app.services import findings_engine, model_fit


def test_params_b_from_catalog_and_name():
    assert model_fit.params_b("gemma3:27b") == 27.0
    assert model_fit.params_b("hf.co/QuantFactory/SecurityLLM-GGUF:Q5_K_M") == 7.0
    assert model_fit.params_b("some-random-13b-model") == 13.0
    assert model_fit.params_b("nomic-embed-text") == 0.137
    assert model_fit.params_b(None) is None
    assert model_fit.params_b("no-size-here") is None


def test_weakness_classification():
    # Assistant-style security model → weak for strict-JSON extraction.
    assert model_fit.is_assistant_style("hf.co/QuantFactory/SecurityLLM-GGUF:Q5_K_M")
    assert model_fit.is_weak_for_extraction("hf.co/QuantFactory/SecurityLLM-GGUF:Q5_K_M")
    # Small generalist → weak.
    assert model_fit.is_weak_for_extraction("mistral:7b")
    # Big generalist → fine.
    assert not model_fit.is_weak_for_extraction("gemma3:27b")
    # Locally-built CyberPal (20B, even with :latest tag) → NOT weak, no false nag.
    assert not model_fit.is_weak_for_extraction("cyberpal2.0-20b:latest")


def test_extraction_warning_only_on_symptom_and_weak_model():
    weak = "hf.co/QuantFactory/SecurityLLM-GGUF:Q5_K_M"
    # No symptom → no nag, even on a weak model.
    assert model_fit.extraction_warning(weak, parse_error=False, empty=False) is None
    # Symptom on a weak model → a recommendation.
    w = model_fit.extraction_warning(weak, parse_error=True, empty=False)
    assert w and "gemma3:27b" in w
    # Symptom on a strong model → no nag (the model isn't the likely cause).
    assert model_fit.extraction_warning("gemma3:27b", parse_error=True, empty=True) is None


def test_weak_model_suffix():
    assert model_fit.weak_model_suffix("gemma3:27b") == ""
    s = model_fit.weak_model_suffix("hf.co/QuantFactory/SecurityLLM-GGUF:Q5_K_M")
    assert s and "gemma3:27b" in s


def test_is_substantive_drops_empty_shells():
    # Title only, everything else empty → shell, dropped.
    assert not findings_engine._is_substantive(
        {"title": "x", "evidence": {}, "mitre": {}, "affected_assets": {}, "affected_users": {}}
    )
    assert not findings_engine._is_substantive({"title": "x", "summary": "  "})
    assert not findings_engine._is_substantive({"summary": "real body"})  # no title
    # A real finding survives.
    assert findings_engine._is_substantive({"title": "x", "summary": "real body"})
    assert findings_engine._is_substantive({"title": "x", "affected_users": ["alice"]})
