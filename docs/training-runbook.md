# Per-Tenant Fine-Tune Runbook (W6)

How to train, evaluate, and promote a per-client model. **Runs offline on your
Apple-Silicon Mac** — it cannot run in CI (needs MLX + Ollama).

Isolation holds throughout: a client's model is trained only on that client's
data and only ever serves that client (Critical Rule #1). Models are
**delete-and-retrain, never reassigned**.

---

## 0. One-time prerequisites (on the Mac)

```bash
cd backend && source venv/bin/activate
pip install mlx-lm                 # Apple-Silicon LoRA trainer + fuse/GGUF export
```

Pick a **Western-origin ~8B** base (32 GB can't LoRA the 27B) and pull it:

```bash
ollama pull llama3.1:8b            # Meta (US)  — or  mistral:7b  (Mistral, FR)
```

The trainer refuses a non-compliant base (cloud / non-Western / community) via
`model_compliance`, the same allowlist the UI enforces.

## 1. Make sure the client has enough signal

In the app: **client → Knowledge Base → Model training data**. You want the
**eligible positives** count to clear the floor (default 200). Sources that fill
it: validated/accepted findings, partial-accept corrections, missed-finding
imports, and — most of all — **Training Hunts** (historic hunts you've ingested).

Also run **Model quality baseline** once (Knowledge Base → Model quality
baseline) so there's a baseline for the promotion gate to compare against.

## 2. Train

```bash
# from repo root
lense train <tenant_id> --base-model llama3.1:8b            # default 600 iters
lense train <tenant_id> --base-model llama3.1:8b --dry-run  # print steps only
```

What it does (all local, tenant-scoped):
1. exports the client's SFT corpus,
2. prepares MLX chat data (train/valid split),
3. LoRA fine-tunes (`mlx_lm.lora`),
4. fuses the adapter into the base and exports GGUF (`mlx_lm.fuse --export-gguf`),
5. imports into Ollama as `lens-tenant-<id>:<tag>` (quantized `q4_K_M`),
6. registers the candidate with status **validating** (never live).

Useful flags: `--iters`, `--num-layers`, `--quantize`, `--no-register`,
`--timestamp <tag>` (the model tag suffix).

## 3. Evaluate (the gate)

In the app: **client → Knowledge Base → Fine-tuned model** → the new candidate
appears as `validating`. Click **Evaluate** — it runs the golden eval against the
candidate and compares it to the baseline. You'll see precision / recall / F1 /
hallucination / parse-error and a **passes / regressed vs baseline** badge.

## 4. Promote (only if it wins)

If it **passes** (no regression), click **Promote**. That makes it the client's
`active` model and retires the previous one. From then on, that client's analysis
**extractor stage** routes to its own model (reviewer/QA stay on the global model
as an unbiased check). If it **regressed**, Promote is blocked server-side.

Routing precedence: active fine-tuned adapter → the client's chosen base model
(Knowledge Base → Base model) → global default.

## 5. Roll back / retire

A promoted model misbehaving? **Reject** or promote a previous version — routing
falls back instantly. To remove entirely: `ollama rm lens-tenant-<id>:<tag>` and
reject it in the registry. To "give a model to another client": you don't —
**train a fresh one from that client's data** (the weights carry the first
client's data; deletion is the only sanitisation).

---

## Notes & gotchas

- **Time/RAM:** an 8B LoRA on 32 GB is feasible but tight — close other models
  first (`lense ollama stop`). Expect minutes-to-tens-of-minutes per run.
- **Too few examples:** the trainer warns below the floor and proceeds only
  because you asked — small sets overfit; review the eval before promoting.
- **GGUF export:** relies on `mlx_lm.fuse --export-gguf`. If your mlx-lm version
  differs, convert the fused model with `llama.cpp` and point the Modelfile
  (`backend/training/_work/tenant_<id>/fused/Modelfile`) at the GGUF, then
  `ollama create` manually.
- **Everything is git-ignored** under `training/` — corpora, adapters, GGUFs are
  client data and never leave the box.
