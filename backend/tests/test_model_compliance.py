"""Model compliance allowlist (W0b)."""
import pytest

from app.services import model_compliance as mc


@pytest.mark.parametrize("name", [
    "gemma3:27b", "mistral-small:24b", "gpt-oss:20b", "nomic-embed-text:latest",
    "nemotron:latest", "llama3.1:8b", "phi3:mini", "mistral:7b",
])
def test_western_families_allowed(name):
    allowed, _ = mc.classify(name)
    assert allowed is True


@pytest.mark.parametrize("name,needle", [
    ("qwen2.5:7b", "non-Western"),
    ("deepseek-coder:6.7b", "non-Western"),
    ("gemma4:31b-cloud", "cloud"),
    ("coney_/gpt-oss_claude-sonnet4.6:latest", "community"),
    ("some-random-model:latest", "allowlist"),
    ("", "empty"),
])
def test_blocked_with_reason(name, needle):
    allowed, reason = mc.classify(name)
    assert allowed is False
    assert needle in reason


def test_is_allowed_helper():
    assert mc.is_allowed("gemma3:27b") is True
    assert mc.is_allowed("qwen2.5:7b") is False
