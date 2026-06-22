"""Tests for global AI-engine config validation (pure, no DB)."""
import pytest

from app.services import global_config


def test_ai_defaults_shape():
    d = global_config.ai_defaults()
    for k in ("base_url", "analyst_model", "reviewer_model", "qa_model", "embed_model",
              "temperature", "timeout"):
        assert k in d


def test_validate_rejects_cloud_models():
    with pytest.raises(ValueError):
        global_config._validate_ai({"analyst_model": "gemma4:31b-cloud"})


def test_validate_clamps_temperature_and_timeout():
    out = global_config._validate_ai({"temperature": "5", "timeout": "1"})
    assert out["temperature"] == 1.0  # clamped to [0,1]
    assert out["timeout"] == 30       # min 30s


def test_validate_ignores_unknown_keys():
    out = global_config._validate_ai({"analyst_model": "gemma3:27b", "bogus": "x"})
    assert out == {"analyst_model": "gemma3:27b"}


def test_current_ai_falls_back_to_defaults():
    assert global_config.current_ai()["analyst_model"]
