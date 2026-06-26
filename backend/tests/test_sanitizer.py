"""Data Sanitizer — deterministic apply + safety net (Tools)."""
from app.services import sanitizer as s


def test_anonymize_consistent_placeholders():
    text = "User jdoe on WKSTN-01 ran a tool; jdoe again on WKSTN-01."
    items = [
        {"value": "jdoe", "type": "username", "action": "anonymize"},
        {"value": "WKSTN-01", "type": "hostname", "action": "anonymize"},
    ]
    out = s.apply(text, items)
    assert "jdoe" not in out["sanitized"] and "WKSTN-01" not in out["sanitized"]
    assert out["sanitized"].count("USER_1") == 2   # consistent + every occurrence
    assert out["sanitized"].count("HOST_1") == 2


def test_secret_is_redacted_not_placeholdered():
    out = s.apply("token=AKIA1234567890SECRET", [
        {"value": "AKIA1234567890SECRET", "type": "token", "action": "redact"},
    ])
    assert "[REDACTED_TOKEN]" in out["sanitized"]
    assert "AKIA1234567890SECRET" not in out["sanitized"]


def test_public_ip_never_touched_even_if_model_lists_it():
    out = s.apply("connect to 8.8.8.8 and 10.0.0.5", [
        {"value": "8.8.8.8", "type": "private_ip", "action": "anonymize"},   # model slip
        {"value": "10.0.0.5", "type": "private_ip", "action": "anonymize"},
    ])
    assert "8.8.8.8" in out["sanitized"]            # public IP preserved
    assert "10.0.0.5" not in out["sanitized"]       # private IP anonymized
    assert any(k["value"] == "8.8.8.8" for k in out["kept"])


def test_external_domain_preserved():
    out = s.apply("beacon to evilcorp.local and login.microsoftonline.com via microsoft.com", [
        {"value": "evilcorp.local", "type": "internal_domain", "action": "anonymize"},
        {"value": "microsoft.com", "type": "internal_domain", "action": "anonymize"},  # slip
    ])
    assert "microsoft.com" in out["sanitized"]      # external kept
    assert "evilcorp.local" not in out["sanitized"] # internal anonymized


def test_longest_first_avoids_partial_replacement():
    # "WKSTN-01" must not be partially mangled when "WKSTN-01-BACKUP" is also a target
    out = s.apply("hosts WKSTN-01-BACKUP and WKSTN-01", [
        {"value": "WKSTN-01", "type": "hostname", "action": "anonymize"},
        {"value": "WKSTN-01-BACKUP", "type": "hostname", "action": "anonymize"},
    ])
    # both fully replaced to distinct placeholders, no leftover fragments
    assert "WKSTN-01-BACKUP" not in out["sanitized"] and "WKSTN-01 " not in out["sanitized"]
    assert "HOST_" in out["sanitized"]


def test_short_values_skipped():
    out = s.apply("a b c", [{"value": "a", "type": "username", "action": "anonymize"}])
    assert out["sanitized"] == "a b c" and out["replacements"] == []
