"""Curated model catalog — lookup + protection helpers (pure)."""
from app.services import model_catalog as mc


def test_catalog_entries_are_well_formed():
    keys = {m["key"] for m in mc.CATALOG}
    assert "foundation-sec-8b" in keys and "nomic-embed-text" in keys
    for m in mc.CATALOG:
        # Every entry must be installable + classifiable by the UI.
        for field in ("key", "name", "ref", "kind", "compliant", "approx_gb"):
            assert field in m, f"{m.get('key')} missing {field}"


def test_by_ref_matches_ref_or_name():
    assert mc.by_ref("nomic-embed-text")["kind"] == "embed"
    assert mc.by_ref("hf.co/QuantFactory/Foundation-Sec-8B-GGUF")["key"] == "foundation-sec-8b"
    assert mc.by_ref("totally-unknown-model") is None


def test_embeddings_is_protected_others_are_not():
    assert mc.is_protected("nomic-embed-text") is True
    assert mc.is_protected("gemma3:27b") is False
    assert mc.is_protected("unknown") is False


def test_recommended_defaults_present():
    rec = {m["key"] for m in mc.CATALOG if m.get("recommended")}
    assert {"foundation-sec-8b", "gemma3-27b", "nomic-embed-text"} <= rec
