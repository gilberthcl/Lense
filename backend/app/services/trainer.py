"""
Per-tenant LoRA trainer service (in-app, W6).

The backend runs on the operator's Apple-Silicon Mac, so it can launch the same
MLX pipeline the CLI does — as a background job driven from the app:

  export corpus → MLX chat data → mlx_lm.lora → fuse+GGUF → ollama create →
  register candidate (status=validating).

Progress is written to a per-tenant status file the UI polls (training is long,
like analysis). It NEVER promotes — the eval gate stays with the operator.

Pure helpers (prepare_mlx_data, build_modelfile) are unit-tested; the
orchestration shells out to mlx_lm/ollama and only runs on the Mac.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

WORK_ROOT = Path("training")
DEFAULT_BASE_MODEL = "llama3.1:8b"


# ── Pure helpers (tested) ────────────────────────────────────────────────────

def prepare_mlx_data(sft_path: Path, out_dir: Path, valid_frac: float = 0.1) -> dict:
    """Convert exported SFT JSONL ({messages, meta}) into an MLX-LM data dir with
    train.jsonl + valid.jsonl (chat format, meta stripped). Deterministic split."""
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
    return {"total": len(rows), "train": len(train), "valid": len(valid), "data_dir": str(out_dir)}


def build_modelfile(gguf_path: str, base_model: str) -> str:
    return (
        f"# Per-tenant fine-tune of {base_model} (LENS)\n"
        f"FROM {gguf_path}\n"
        f"PARAMETER temperature 0.2\n"
        f"PARAMETER num_ctx 12288\n"
    )


# ── Status file (UI polls this) ──────────────────────────────────────────────

def status_path(tenant_id: int) -> Path:
    return WORK_ROOT / f"tenant_{tenant_id}" / "train_status.json"


def write_status(tenant_id: int, data: dict) -> None:
    p = status_path(tenant_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_status(tenant_id: int) -> dict | None:
    p = status_path(tenant_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ── Orchestration (Mac-only) ─────────────────────────────────────────────────

StepFn = Callable[[str, int], None]


def _run(cmd: list[str], *, dry: bool) -> None:
    if dry:
        return
    subprocess.run(cmd, check=True)


def run_training(
    db: Session, tenant_id: int, *, base_model: str = DEFAULT_BASE_MODEL,
    iters: int = 600, num_layers: int = 16, quantize: str = "q4_K_M",
    tag: str = "v", register: bool = True, dry_run: bool = False,
    on_step: StepFn | None = None,
) -> dict:
    """Run the full pipeline. Returns the registered candidate info."""
    from app.services import model_compliance, tenant_models, training_export
    step: StepFn = on_step or (lambda msg, pct=0: None)

    allowed, reason = model_compliance.classify(base_model)
    if not allowed:
        raise ValueError(f"Base model '{base_model}' is not allowed — {reason}.")

    step("Exporting this client's training corpus…", 8)
    stats = training_export.export_tenant(db, tenant_id)
    sft_path = Path(stats["written"]["sft_path"])
    n = stats["written"]["sft_examples"]
    if n == 0:
        raise ValueError("No training examples yet — validate findings or import a training hunt first.")
    step(f"Exported {n} example(s).", 15)

    work = WORK_ROOT / f"tenant_{tenant_id}" / "_work"
    data_dir, adapters, fused = work / "data", work / "adapters", work / "fused"
    gguf = fused / "model.gguf"

    prep = prepare_mlx_data(sft_path, data_dir)
    step(f"Prepared {prep['train']} train / {prep['valid']} valid example(s).", 22)

    step(f"LoRA fine-tuning {base_model} ({iters} iters)… this is the long step.", 30)
    _run([sys.executable, "-m", "mlx_lm.lora", "--model", base_model, "--train",
          "--data", str(data_dir), "--iters", str(iters),
          "--num-layers", str(num_layers), "--adapter-path", str(adapters)], dry=dry_run)

    step("Fusing adapter + exporting GGUF…", 72)
    _run([sys.executable, "-m", "mlx_lm.fuse", "--model", base_model,
          "--adapter-path", str(adapters), "--save-path", str(fused),
          "--export-gguf", "--gguf-path", "model.gguf"], dry=dry_run)

    ollama_name = f"lens-tenant-{tenant_id}:{tag}"
    step("Importing into Ollama…", 86)
    if not dry_run:
        fused.mkdir(parents=True, exist_ok=True)
        (fused / "Modelfile").write_text(build_modelfile(str(gguf), base_model), encoding="utf-8")
    _run(["ollama", "create", ollama_name, "-f", str(fused / "Modelfile"),
          "--quantize", quantize], dry=dry_run)

    if not register or dry_run:
        step("Dry run complete (not registered).", 100)
        return {"ollama_model_name": ollama_name, "examples": n, "registered": False}

    model = tenant_models.register(
        db, tenant_id, base_model=base_model, ollama_model_name=ollama_name,
        train_metrics={"iters": iters, "examples": n, "num_layers": num_layers},
        notes="Trained from the app (Train button).",
    )
    step(f"Registered candidate v{model.version} — now Evaluate it, then Promote if it wins.", 100)
    return {"model_id": model.id, "version": model.version,
            "ollama_model_name": ollama_name, "examples": n, "registered": True}


def start_background(tenant_id: int, base_model: str, tag: str) -> None:
    """Entry point for the API BackgroundTask — owns its DB session and writes
    progress to the status file."""
    from app.core.db import SessionLocal
    db = SessionLocal()

    def on_step(msg: str, pct: int = 0) -> None:
        prev = read_status(tenant_id) or {}
        log = (prev.get("log") or []) + [msg]
        write_status(tenant_id, {"status": "running", "step": msg, "pct": pct,
                                 "base_model": base_model, "log": log[-30:]})

    try:
        result = run_training(db, tenant_id, base_model=base_model, tag=tag, on_step=on_step)
        write_status(tenant_id, {"status": "done", "pct": 100, "base_model": base_model, **result})
    except Exception as exc:  # noqa: BLE001 — surface in the status file
        write_status(tenant_id, {"status": "error", "error": str(exc), "base_model": base_model})
    finally:
        db.close()
