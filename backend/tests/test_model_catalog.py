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


def test_build_only_entry_carries_a_command_and_resolves_by_local_name():
    cp = mc.by_ref("hf.co/cyber-pal-security/CyberPal2.0-20B")
    assert cp and cp["key"] == "cyberpal-20b"
    assert cp.get("build_only") is True
    assert cp.get("build_cmd")  # the operator needs the exact command
    # After the local build it registers as `ollama_name`; that must still resolve
    # to the vetted catalog entry so compliance recognises it as allowed.
    assert mc.by_ref("cyberpal2.0-20b")["key"] == "cyberpal-20b"


def test_locally_built_model_passes_compliance():
    from app.services import model_compliance
    allowed, _ = model_compliance.classify("cyberpal2.0-20b")
    assert allowed is True  # via the vetted-catalog exception (ollama_name match)
