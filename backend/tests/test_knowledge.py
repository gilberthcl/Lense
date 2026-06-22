"""Unit tests for KB chunking + retrieval-query construction (no DB/Ollama)."""
from app.services import knowledge
from app.services.analysis_runner import _retrieval_query


class _Hunt:
    name = "Lateral Movement Hunt"
    methodology_brief = {"hunt_overview": "Hunting SMB and RDP lateral movement."}


class _Dataset:
    filename = "smb_logons.csv"


def test_chunk_text_short_returns_single():
    assert knowledge.chunk_text("small text") == ["small text"]
    assert knowledge.chunk_text("") == []


def test_chunk_text_splits_with_overlap():
    para = "\n\n".join(f"Paragraph {i} " + ("x" * 300) for i in range(10))
    chunks = knowledge.chunk_text(para, size=500, overlap=80)
    assert len(chunks) > 1
    assert all(len(c) <= 500 + 80 for c in chunks)  # bounded by size(+overlap tail)


def test_chunk_text_hard_splits_oversized_paragraph():
    giant = "y" * 5000
    chunks = knowledge.chunk_text(giant, size=1000, overlap=100)
    assert len(chunks) >= 5
    assert chunks[0] == "y" * 1000


def test_format_context_empty():
    assert knowledge.format_context([]) == ""


def test_format_context_renders_chunks():
    out = knowledge.format_context(
        [{"doc_type": "validated_finding", "title": "F-001", "text": "evil.exe seen"}]
    )
    assert "PRIOR KNOWLEDGE" in out
    assert "validated_finding" in out and "evil.exe seen" in out


def test_retrieval_query_includes_signals():
    evidence = {
        "schema": ["ComputerName", "UserName", "CommandLine"],
        "entities": {"hosts": ["WKSTN-01"], "users": ["jdoe"]},
    }
    q = _retrieval_query(_Hunt(), _Dataset(), evidence)
    assert "Lateral Movement Hunt" in q
    assert "smb_logons.csv" in q
    assert "WKSTN-01" in q and "jdoe" in q
    assert "ComputerName" in q
