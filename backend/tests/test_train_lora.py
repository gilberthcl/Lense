"""Trainer data-prep + Modelfile helpers (W6, pure — no MLX/Ollama)."""
import json

from tools import train_lora as tl


def _write_sft(path, n):
    lines = []
    for i in range(n):
        lines.append(json.dumps({
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": f"u{i}"},
                {"role": "assistant", "content": f"a{i}"},
            ],
            "meta": {"finding_ref": f"F-{i}"},
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_prepare_splits_and_strips_meta(tmp_path):
    sft = tmp_path / "x.sft.jsonl"
    _write_sft(sft, 20)
    out = tmp_path / "data"
    stats = tl.prepare_mlx_data(sft, out, valid_frac=0.1)
    assert stats["total"] == 20
    assert stats["train"] + stats["valid"] == 20
    assert stats["valid"] > 0 and stats["train"] > 0
    # meta stripped; only {"messages": [...]} remains
    first = json.loads((out / "train.jsonl").read_text().splitlines()[0])
    assert set(first.keys()) == {"messages"}
    assert first["messages"][0]["role"] == "system"


def test_prepare_tiny_set_keeps_train_nonempty(tmp_path):
    sft = tmp_path / "x.sft.jsonl"
    _write_sft(sft, 1)
    stats = tl.prepare_mlx_data(sft, tmp_path / "d", valid_frac=0.1)
    assert stats["train"] == 1  # never let valid swallow the only row


def test_prepare_skips_blank_and_bad_lines(tmp_path):
    sft = tmp_path / "x.sft.jsonl"
    sft.write_text('\n{"messages":[{"role":"user","content":"hi"}]}\nnot-json\n{"meta":1}\n',
                   encoding="utf-8")
    stats = tl.prepare_mlx_data(sft, tmp_path / "d")
    assert stats["total"] == 1  # only the one valid messages row


def test_build_modelfile():
    mf = tl.build_modelfile("/x/model.gguf", "llama3.1:8b")
    assert "FROM /x/model.gguf" in mf
    assert "llama3.1:8b" in mf
