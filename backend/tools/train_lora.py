"""
Per-tenant LoRA trainer CLI (W6) — thin wrapper over services.trainer.

Runs OFFLINE on the operator's Apple-Silicon Mac. The same pipeline is also
launchable from the app (the Train button). See docs/training-runbook.md.

Usage (from backend/, venv active):
    python -m tools.train_lora <tenant_id> --base-model llama3.1:8b [--iters 600] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys

from app.services import trainer


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-tenant LoRA trainer (offline, Mac).")
    ap.add_argument("tenant_id", type=int)
    ap.add_argument("--base-model", default=trainer.DEFAULT_BASE_MODEL)
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--num-layers", type=int, default=16)
    ap.add_argument("--quantize", default="q4_K_M")
    ap.add_argument("--tag", default="manual", help="ollama model tag suffix")
    ap.add_argument("--no-register", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    from app.core.db import SessionLocal
    db = SessionLocal()
    try:
        result = trainer.run_training(
            db, args.tenant_id, base_model=args.base_model, iters=args.iters,
            num_layers=args.num_layers, quantize=args.quantize, tag=args.tag,
            register=not args.no_register, dry_run=args.dry_run,
            on_step=lambda msg, pct=0: print(f"[{pct:3d}%] {msg}"),
        )
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
