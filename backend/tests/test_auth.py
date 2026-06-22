"""Unit tests for the local access-PIN service (no DB)."""
from app.services import auth


def test_hash_is_deterministic_and_salted():
    h1 = auth.hash_pin("123456")
    h2 = auth.hash_pin("123456")
    assert h1 == h2
    assert h1 != "123456"            # not stored in clear
    assert auth.hash_pin("654321") != h1


def test_check_allows_when_unconfigured(monkeypatch):
    monkeypatch.setattr(auth, "_pin_hash", None)
    assert auth.configured() is False
    assert auth.check("anything") is True  # bootstrap: open until a PIN is set


def test_check_requires_matching_token_when_configured(monkeypatch):
    h = auth.hash_pin("abc123")
    monkeypatch.setattr(auth, "_pin_hash", h)
    assert auth.configured() is True
    assert auth.check(h) is True
    assert auth.check("wrong") is False
    assert auth.check("") is False
