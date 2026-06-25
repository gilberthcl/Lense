"""Ollama transient-failure retry policy."""
import pytest

from app.services import ollama_client as oc


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(oc.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(oc, "_retries", lambda: 2)


def test_transient_error_is_retried_then_succeeds():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise oc.OllamaError("connection reset")  # retryable by default
        return "ok"

    assert oc._with_retries("x", fn) == "ok"
    assert calls["n"] == 3  # failed twice, third attempt succeeded


def test_timeout_is_not_retried():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        err = oc.OllamaError("timed out")
        err.retryable = False
        raise err

    with pytest.raises(oc.OllamaError):
        oc._with_retries("x", fn)
    assert calls["n"] == 1  # no retries on timeout


def test_retries_are_bounded():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise oc.OllamaError("reset")

    with pytest.raises(oc.OllamaError):
        oc._with_retries("x", fn)
    assert calls["n"] == 3  # 1 initial + 2 retries
