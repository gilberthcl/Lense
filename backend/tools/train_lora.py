"""
Per-tenant LoRA trainer (W6) — runs OFFLINE on the operator's Apple-Silicon Mac.

Pipeline (all local, tenant-scoped):
  1. export the tenant's SFT corpus      (services.training_export)
  2. prepare MLX-LM chat data (train/valid split)
  3. LoRA fine-tune                       (mlx_lm.lora)
  4. fuse adapter into the base + GGUF    (mlx_lm.fuse --export-gguf)
  5. import into Ollama                   (ollama create lens-tenant-<id>:<ver>)
  6. register the candidate               (services.tenant_models.register, status=validating)

Then, in the app: run the model's Evaluate (golden eval vs baseline) and Promote
if it didn't regress. This script NEVER promotes — the gate stays with the operator.

This file is intentionally runnable but CANNOT be exercised in CI (needs MLX +
Apple Silicon + Ollama). The data-prep + Modelfile helpers are pure and tested.

Usage (from backend/, venv active):
    python -m tools.train_lora <tenant_id> --base-model llama3.1:8b [--iters 600] [--dry-run]

Prereqs on the Mac:
    pip install mlx-lm        # Apple-Silicon LoRA trainer
    ollama pull <base-model>  # a Western-origin ~8B (see model_compliance)
See docs/training-runbook.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


# ── Pure helpers (tested) ────────────────────────────────────────────────────

def prepare_mlx_data(sft_path: Path, out_dir: Path, valid_frac: float = 0.1) -> dict:
    """Convert the exported SFT JSONL ({messages, meta}) into an MLX-LM data dir
    with train.jsonl + valid.jsonl (chat format, meta stripped). Deterministic
    split (every Nth line → valid) so re-runs are stable."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for line in sft_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msgs = obj.get("messages")
        if isinstance(msgs, list) and msgs:
            rows.append({"messages": msgs})

    stride = max(2, int(round(1 / valid_frac))) if valid_frac > 0 else 0
    train, valid = [], []
    for i, r in enumerate(rows):
        (valid if stride and (i % stride == 0) else train).append(r)
    # Never let valid swallow everything on tiny sets.
    if not train and valid:
        train, valid = valid, []

    (out_dir / "train.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in train) + ("\n" if train else ""),
        encoding="utf-8",
    )
    (out_dir / "valid.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in valid) + ("\n" if valid else ""),
        encoding="utf-8",
    )
    return {"total": len(rows), "train": len(train), "valid": len(valid),
            "data_dir": str(out_dir)}


def build_modelfile(gguf_path: str, base_model: str) -> str:
    """A minimal Ollama Modelfile pointing at the fused GGUF."""
    return (
        f"# Per-tenant fine-tune of {base_model} (LENS W6)\n"
        f"FROM {gguf_path}\n"
        f'PARAMETER temperature 0.2\n'
        f'PARAMETER num_ctx 12288\n'
    )


# ── Orchestration (Mac-only) ─────────────────────────────────────────────────

def _run(cmd: list[str], *, dry: bool) -> None:
    print("›", " ".join(cmd))
    if dry:
        return
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-tenant LoRA trainer (offline, Mac).")
    ap.add_argument("tenant_id", type=int)
    ap.add_argument("--base-model", required=True, help="Western-origin ~8B, e.g. llama3.1:8b")
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--num-layers", type=int, default=16, help="LoRA layers to train")
    ap.add_argument("--workdir", default="training/_work")
    ap.add_argument("--quantize", default="q4_K_M", help="Ollama quantization on import")
    ap.add_argument("--timestamp", default="manual", help="tag suffix (CI-safe: no clock here)")
    ap.add_argument("--no-register", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print steps without running")
    args = ap.parse_args(argv)

    # Compliance gate on the base model — never train a non-Western/cloud base.
    from app.services import model_compliance
    allowed, reason = model_compliance.classify(args.base_model)
    if not allowed:
        print(f"ERROR: base model '{args.base_model}' is not allowed — {reason}.", file=sys.stderr)
        return 2

    from app.core.db import SessionLocal
    from app.services import training_export, tenant_models

    db = SessionLocal()
    try:
        # 1. Export the tenant's corpus.
        stats = training_export.export_tenant(db, args.tenant_id)
        sft_path = Path(stats["written"]["sft_path"])
        n = stats["written"]["sft_examples"]
        print(f"Exported {n} SFT example(s) → {sft_path}")
        if not stats["ready_for_training"]:
            print(f"WARNING: only {n} examples (< {stats['min_validated']} floor) — "
                  "likely to overfit. Proceeding because you asked; review the result carefully.")
        if n == 0:
            print("No training examples — nothing to do.", file=sys.stderr)
            return 1

        work = Path(args.workdir) / f"tenant_{args.tenant_id}"
        data_dir = work / "data"
        adapters = work / "adapters"
        fused = work / "fused"
        gguf = fused / "model.gguf"

        prep = prepare_mlx_data(sft_path, data_dir)
        print(f"Prepared MLX data: {prep['train']} train / {prep['valid']} valid")

        # 3. LoRA fine-tune.
        _run([sys.executable, "-m", "mlx_lm.lora", "--model", args.base_model,
              "--train", "--data", str(data_dir), "--iters", str(args.iters),
              "--num-layers", str(args.num_layers), "--adapter-path", str(adapters)],
             dry=args.dry_run)

        # 4. Fuse + export GGUF.
        _run([sys.executable, "-m", "mlx_lm.fuse", "--model", args.base_model,
              "--adapter-path", str(adapters), "--save-path", str(fused),
              "--export-gguf", "--gguf-path", "model.gguf"], dry=args.dry_run)

        # 5. Ollama import.
        ollama_name = f"lens-tenant-{args.tenant_id}:{args.timestamp}"
        modelfile = fused / "Modelfile"
        print(f"Writing {modelfile}")
        if not args.dry_run:
            fused.mkdir(parents=True, exist_ok=True)
            modelfile.write_text(build_modelfile(str(gguf), args.base_model), encoding="utf-8")
        _run(["ollama", "create", ollama_name, "-f", str(modelfile),
              "--quantize", args.quantize], dry=args.dry_run)

        # 6. Register the candidate (status=validating). No promotion here.
        if args.no_register or args.dry_run:
            print(f"(skipped register) candidate model: {ollama_name}")
            return 0
        model = tenant_models.register(
            db, args.tenant_id, base_model=args.base_model,
            ollama_model_name=ollama_name,
            train_metrics={"iters": args.iters, "examples": n, "num_layers": args.num_layers},
            notes="Trained via tools/train_lora.py",
        )
        print(f"Registered candidate v{model.version} ({ollama_name}) — status: {model.status}.")
        print("Next: open the client → Fine-tuned model → Evaluate, then Promote if it beats baseline.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
