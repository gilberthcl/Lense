"""Tests for canonical finding-category normalization."""
from app.services import categories


def test_canonical_keys_unique_and_complete():
    keys = [c["key"] for c in categories.CATEGORIES]
    assert len(keys) == len(set(keys)) == 8
    # every category carries bilingual labels
    assert all(c["label_en"] and c["label_es"] for c in categories.CATEGORIES)


def test_normalize_exact_keys():
    assert categories.normalize("malicious") == "malicious"
    assert categories.normalize("policy_violation") == "policy_violation"
    assert categories.normalize("no_finding") == "no_finding"


def test_normalize_english_labels():
    assert categories.normalize("Malicious Activity Identified") == "malicious"
    assert categories.normalize("Potential Policy Violation Identified") == "policy_violation"
    assert categories.normalize("Vulnerable Configuration Identified") == "vulnerable_configuration"
    assert categories.normalize("New Hunting Opportunity Identified") == "new_hunting_opportunity"
    assert categories.normalize("Potential Baseline Activity Identified") == "baseline"


def test_normalize_spanish_labels():
    assert categories.normalize("Actividad Maliciosa Identificada") == "malicious"
    assert categories.normalize("Configuración Vulnerable Identificada") == "vulnerable_configuration"


def test_normalize_aliases_and_fallbacks():
    assert categories.normalize("Informational") == "unconfirmed"
    assert categories.normalize("hunting opportunity") == "new_hunting_opportunity"
    assert categories.normalize("") == "unconfirmed"
    assert categories.normalize(None) == "unconfirmed"
    # noisy substring still resolves
    assert categories.normalize("Malicious activity on host WKSTN-01") == "malicious"
