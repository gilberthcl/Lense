# Design Doc — Per-Tenant LoRA Fine-Tuning (Phase 2, proposed)

Status: **Proposal / not implemented.** This is a scoping document, not a commitment.
Author context: LENS Threat Hunt Findings Engine.
Related rule: CLAUDE.md Critical Rule #1 (tenant isolation), #2 (evidence only),
#5 (learning without retraining).

---

## 1. Problem & goal

Today LENS improves outcomes three ways, none of which change model weights:
prompt engineering, deterministic workflow, and **RAG** (validated findings are
embedded into a per-tenant knowledge base and retrieved into the analyst prompt
— see `app/services/knowledge.py`). The model `gemma3:27b` is frozen.

The goal of this proposal: let a tenant's accumulated, human-validated findings
**also** shape the model's weights — so the analyst internalizes a client's
environment, naming, and judgment, not just receives it as prompt context —
**without breaking tenant isolation, evidence discipline, or local-only
compliance.**

This is explicitly an *addition* to RAG, not a replacement. RAG stays the
primary, always-on learning loop; fine-tuning is an optional per-tenant boost.

## 2. The one non-negotiable: isolation forces per-tenant adapters

A single fine-tuned model shared across tenants would bake Client A's hosts,
users, and IPs into weights that then serve Client B. That is a direct
violation of Critical Rule #1.

**Therefore the only admissible design is one LoRA adapter per tenant**, trained
only on that tenant's data, stored scoped to `tenant_id`, and loaded only when
analyzing that tenant's hunts. The shared base model stays generic and is never
trained. A LoRA adapter is a small (~tens–hundreds of MB) weight-delta layered
on top of the frozen base — cheap to store and swap, which is what makes
per-tenant feasible at all.

## 3. Why LoRA + MLX + Ollama (the local-Mac reality)

- **Ollama cannot train** — it is inference-only. Training needs a separate
  toolchain.
- **MLX-LM** (Apple's framework) is the only training stack that runs well on
  Apple Silicon. Unsloth/axolotl are CUDA/NVIDIA-only and don't apply on the
  operator's Mac.
- **Hardware ceiling:** a 32 GB Mac cannot LoRA-tune a 27B model with any
  headroom. Realistic base for *training* is a **7–8B** model (e.g.
  `llama3.1:8b` / a Western-origin 8B). Inference of the tuned 8B is then cheap.
  → **Implication:** the fine-tuned path likely runs a *smaller* model than the
  27B analyst. It is a specialization trade (a small model that knows *this*
  client) vs. a big generalist. This must be measured, not assumed better.
- **Serving:** MLX adapter → fuse into base → convert to **GGUF** → `ollama
  create` a per-tenant model. Ollama then serves it like any other model, so the
  rest of LENS (which already calls Ollama) needs almost no change at inference
  time beyond *which model name* it picks.

## 4. Architecture overview

```
 Validated findings (per tenant)
        │  (export)
        ▼
 [1] Training-set exporter ──► JSONL SFT pairs (input → approved finding)
        │                       + rejected findings as hard-negative guidance
        ▼
 [2] Offline MLX-LM LoRA trainer  (runs out-of-band; NOT in the request path)
        │  adapter.safetensors
        ▼
 [3] Fuse + convert ──► GGUF ──► `ollama create lens-tenant-<id>:<ver>`
        │
        ▼
 [4] Adapter registry  (tenant_id → model name + version + metrics + status)
        │
        ▼
 [5] Inference routing: analysis picks the tenant's model IF status=active,
        else falls back to the global analyst model
        │
        ▼
 [6] Evidence-discipline re-validation gate  (must pass before status=active)
```

Key property: steps **1–3 are offline batch jobs**. Nothing here runs inside an
analysis request. The live pipeline only ever *reads* the registry (step 5).

## 5. Components

### [1] Training-set exporter  (`services/training_export.py`, new)
- Pull `Finding` rows for one tenant where `status == "validated"`, join their
  `dataset`/evidence, and emit **SFT pairs**: the prompt we *would* have sent
  (evidence package + methodology context) → the human-approved finding JSON.
- Also export `status == "rejected"` findings as **negative/contrastive**
  examples ("this was flagged but is a false positive because…"). Today these
  are discarded; they are the richest FP-discipline signal we have.
- Output: tenant-scoped JSONL under `training/tenant_<id>/<timestamp>.jsonl`.
  Never commit (same policy as `uploads/`).
- Hard gate: refuse to export if fewer than **N** validated findings (LoRA on a
  handful of examples overfits and damages the model). Suggested floor N≈200,
  tuned empirically.

### [2] Offline trainer  (`tools/train_lora.py`, new — CLI, not an API)
- Wraps `mlx_lm.lora` with sane defaults (rank, learning rate, iters, a
  held-out validation split). Reads one tenant's JSONL, writes an adapter.
- Invoked via `lense train <tenant>` — **manual, deliberate, logged**. Never
  triggered automatically by validation events (unlike RAG indexing, which is
  instant and safe).
- Emits training metrics (loss curve, val loss) into the registry row.

### [3] Fuse + convert  (part of the same CLI)
- `mlx_lm.fuse` → merge adapter into base; convert to GGUF; `ollama create`
  with a generated `Modelfile`. Produces `lens-tenant-<id>:<version>`.

### [4] Adapter registry  (new table `tenant_models`)
```
tenant_models
  id, tenant_id (FK, indexed), base_model, ollama_model_name, version,
  status (draft|validating|active|rejected|retired),
  train_metrics (JSON), eval_metrics (JSON),
  trained_at, activated_at
```
- At most one `active` row per tenant. Versioned so a regression can roll back
  to the previous adapter instantly (just flip `status`).

### [5] Inference routing  (small change to `global_config` + `analysis_runner`)
- `current_ai()` currently returns a global `analyst_model`. Add a
  resolver `analyst_model_for(tenant_id)` that returns the tenant's
  `active` model name if present, else the global default.
- `findings_engine`/`ollama_client` already take the model as a parameter, so
  this is a routing change, not a pipeline rewrite.
- Reviewer/QA stages **stay on the global model** initially — we only specialize
  the extractor, where client-specific knowledge matters most, and keep an
  unbiased reviewer as a check.

### [6] Evidence-discipline re-validation gate  (reuse, don't rebuild)
- A freshly tuned model is `status=validating`, **not** live.
- Run a fixed **golden eval set** (a frozen set of datasets with known-good
  findings, ideally cross-tenant-safe synthetic + that tenant's holdout) through
  the candidate model and assert:
  - hallucination/`dropped_unsupported` rate did **not** rise vs. the base,
  - finding recall/precision vs. human labels did **not** regress,
  - JSON parse-failure rate did not rise.
- Only on pass does an operator promote it to `active`. This directly defends
  Critical Rule #2 against fine-tuning's tendency to "generate from memory."

## 6. Data model & isolation summary

- New: `tenant_models` (above). Everything keyed by `tenant_id`.
- Training data, adapters, and GGUFs live under tenant-scoped paths and are
  git-ignored (client data).
- The base model is shared and never trained. Adapters are never shared.
- A tenant delete must cascade: registry rows, on-disk adapters/GGUFs, and the
  `ollama rm lens-tenant-<id>:*` models.

## 7. Risks & failure modes

| Risk | Mitigation |
|---|---|
| Tenant data leaks into a shared model | Per-tenant adapters only; base never trained; isolation tests |
| Fine-tune erodes evidence discipline (more hallucination) | Re-validation gate [6]; specialize extractor only; keep reviewer unbiased |
| 8B-tuned < 27B-generalist in quality | A/B the candidate vs. current pipeline on the golden set before activ_ation; keep instant rollback |
| Overfitting on few examples | Minimum-N export gate; held-out val loss; LoRA (not full FT) |
| Operator confusion / silent model swap | Registry status is explicit; UI shows which model analyzed each hunt |
| Compliance (model provenance) | Base must stay Western-origin (Rule: no `*-cloud`, no unverified provenance) |

## 8. What this does NOT do
- Does not replace RAG. RAG remains the default learning loop.
- Does not fine-tune the 27B analyst (hardware).
- Does not auto-train on validation. Training is a manual, gated, offline act.
- Does not touch reviewer/QA models in v1.

## 9. Phased rollout
1. **Exporter + dataset inspection** ([1]). **DONE** — `services/training_export.py`,
   `api/training.py`, `TrainingPanel` under the client's Knowledge Base tab.
2. **Golden eval harness** ([6]) against the *current* model. **DONE** —
   `services/eval_metrics.py` (pure scoring), `services/eval_runner.py`
   (synthetic golden cases + per-tenant holdout + `run_eval`), `api/eval.py`,
   `EvalPanel`. Establishes the baseline metrics we must not regress.
3. **Trainer + registry + routing** ([2]–[5]) behind a feature flag, one pilot
   tenant. **NEXT** — needs decisions #1 (base model) below; runs on the
   operator's Mac with MLX (cannot be exercised in CI).
4. Measure vs. baseline (`eval_metrics.compare`). Promote only if it wins. Iterate.

## 10. Decisions needed before building
- **Base model for training** — 8B Western-origin candidate? (affects feasibility)
- **Minimum validated-finding count** to allow a train (overfit floor).
- **Specialize extractor only, or also writer?**
- **Golden eval set source** — synthetic, per-tenant holdout, or both?
- Is the likely outcome (a smaller specialized model) acceptable vs. today's 27B,
  pending measurement?

---

### TL;DR
RAG already gives isolation-safe "learning without retraining." If we want
weight-level learning too, the *only* compliant shape is **per-tenant LoRA
adapters**, trained **offline with MLX on a smaller base**, served via Ollama,
and **gated by an evidence-discipline re-validation** before going live. Build
the exporter and eval harness first; they're useful and risk-free, and they tell
us whether the full path is even worth it.
