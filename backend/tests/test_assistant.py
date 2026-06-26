"""Sable assistant — pure helpers (cosine, rank, prompt assembly)."""
from types import SimpleNamespace

from app.services import assistant as a


def test_cosine_basic_and_degenerate():
    assert a.cosine([1, 0], [1, 0]) == 1.0
    assert a.cosine([1, 0], [0, 1]) == 0.0
    assert a.cosine([], [1]) == 0.0          # empty
    assert a.cosine([0, 0], [1, 1]) == 0.0   # zero vector


def test_rank_returns_top_k_above_threshold():
    rows = [
        SimpleNamespace(id=1, embedding=[1.0, 0.0]),     # identical → sim 1
        SimpleNamespace(id=2, embedding=[0.9, 0.1]),     # close
        SimpleNamespace(id=3, embedding=[0.0, 1.0]),     # orthogonal → dropped (<0.3)
        SimpleNamespace(id=4, embedding=None),           # no embedding → skipped
    ]
    top = a.rank([1.0, 0.0], rows, k=2)
    assert [r.id for r in top] == [1, 2]


def test_build_prompt_includes_context_history_and_question():
    examples = [SimpleNamespace(question="What is T1110?", answer="Brute force.")]
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    p = a.build_prompt("Explain password spraying", history, examples)
    assert "Brute force." in p                       # retrieved context
    assert "Analyst: hi" in p and "Sable: hello" in p  # history, labelled
    assert "Explain password spraying" in p          # the question


def test_build_prompt_is_clean_with_no_context_or_history():
    p = a.build_prompt("What is KQL?", None, [])
    assert p.strip().endswith("What is KQL?")
    assert "Highly-rated" not in p and "Conversation so far" not in p
