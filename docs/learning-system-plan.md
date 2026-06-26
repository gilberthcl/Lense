# LENS Learning System — Consolidated Build Plan

Status: **Plan / approved scope, phased build.** Supersedes the roadmap section of
`per-tenant-lora-finetuning.md` (that doc's mechanics still apply). No code in
this file — it is the blueprint for several build sessions.

This plan folds three operator decisions into one architecture:
1. **Per-client isolated models**, learning *analytical skill* first, environment second.
2. **Rich feedback** at every stage (accept / reject / partial-accept / score, all with feedback) + a **missed-finding** path.
3. **Training Hunts** — years of historic, expert-validated hunts as the foundational corpus.

---

## 0. Non-negotiable invariants (hard gates on every workstream)

These are checked on every PR in this plan. A violation blocks the merge.

- **DB isolation is absolute.** Every table carries `tenant_id`; every query
  filters by it. No join, export, training set, eval set, RAG retrieval, or model
  ever mixes two tenants' data. (Critical Rule #1.)
- **Per-client models are permanent and one-way bound.** A model trained on
  Client A's data serves only Client A, forever. There is **no transfer/reassign
  operation**. "Uninstall" = delete the model + adapter + registry row; to serve
  another client you **train a fresh model from that client's data**. (The weights
  carry the data; deletion is the only sanitisation.)
- **Evidence discipline is preserved.** Findings cite only values in the evidence
  package. Fine-tuning may never raise the hallucination rate past the baseline —
  enforced by the promotion gate (`eval_metrics.compare`).
- **No model goes live without beating its baseline.** Promotion is gated.
- **Two learning channels, always both:**
  - **RAG (immediate):** every learning signal is also written to the per-tenant
    knowledge base, so the model improves on the *next hunt* with no training.
  - **Fine-tune (deferred):** the same signal becomes labelled training data for
    that client's model.

## 1. What already exists (Phases 1–3, built)

| Built | Where | Reused for |
|---|---|---|
| Training-set exporter | `services/training_export.py`, `api/training.py`, `TrainingPanel` | Corpus assembly |
| Golden-eval harness + gate | `services/eval_metrics.py`, `eval_runner.py`, `api/eval.py`, `EvalPanel` | Baseline + promotion gate |
| Per-tenant model registry + routing | `models.TenantModel`, `services/tenant_models.py`, `api/models.py`, `ModelsPanel` | Per-client model lifecycle |
| RAG learning loop | `services/knowledge.py` (validated findings → embedded context) | Immediate channel |

Still missing: the MLX trainer (needs base-model choice + the Mac), the rich
feedback surfaces, Training Hunts, and all-stages learning.

---

## 2. The learning spine (shared data model)

Everything below produces **Learning Signals**. We add one spine so every source
feeds both channels uniformly.

- **`LearningEvent`** (new table, tenant-scoped) — the unifying record:
  `{tenant_id, hunt_id, stage, target_type, target_id, disposition, score,
  feedback_text, summary, source, created_at, author}`.
  - `stage` ∈ methodology | plan | analysis | correlation | qa | writing | finding
  - `disposition` ∈ accepted | partial | rejected | added (missed-finding) | n/a
  - `source` ∈ live_feedback | training_hunt | missed_finding | import
- **Finding** gains `disposition`, `score`, and links to its revision history.
- **`FindingRevision`** (new, tenant-scoped) — every partial-accept regeneration:
  `{finding_id, version, content, feedback_text, created_at}`. The before→feedback→after
  chain is premium training data.
- **`Hunt.kind`** ∈ live | training — Training Hunts never emit live client findings.
- **Missed findings** = a Finding with `source = analyst_added` + a stored
  "why-missed" analysis.

Isolation: all new tables `tenant_id`-indexed, cascade on tenant delete, and are
added to the isolation test harness (W0).

Migration note: dev uses `Base.metadata.create_all` (new tables auto-create);
**new columns on existing tables require a real migration** — W0 introduces
Alembic (CLAUDE.md already flags this as the Phase-2 trigger).

---

## 3. Workstreams (each shippable on its own)

### W0 — Foundations: isolation harness + learning spine + Alembic
**Goal:** lay the data model and lock the isolation guarantees before adding surfaces.
- `LearningEvent`, `FindingRevision`, `Hunt.kind`, `Finding.disposition/score`.
- Introduce **Alembic** (first real migration; needed for new columns).
- **Isolation test harness:** a reusable test that asserts no service returns
  cross-tenant rows; run it against every learning query.
- Unified `learning.record_event()` that writes the event **and** mirrors it into
  RAG knowledge (immediate channel) in one call.
- Testable here: ✅ fully. Needs Mac: ❌.

### W1 — Rich finding disposition loop *(point 2 core; highest-frequency signal)*
**Goal:** replace the bare accept/reject with the full loop, on findings first.
- **Reject** (feedback required) · **Accept** (feedback optional) · **Score 1–10** on every disposition.
- **Partial-accept:** capture feedback → **regenerate the finding** from it (reuse
  the QA "re-run with feedback" plumbing) → store a `FindingRevision` → repeat until
  the analyst accepts. The correction chain is exported as premium pairs.
- Each disposition → `learning.record_event()` → RAG (now) + exporter (later).
- **Scoring semantics (honest):** the 1–10 score is a **curation/weighting** signal,
  not RL reward — it decides what enters training (high accepts = positives;
  rejects/low = negatives; accepted-vs-rejected = preference pairs). No literal
  weight penalisation (not local-feasible).
- UI: rework the Findings tab disposition controls + a feedback modal.
- Testable here: ✅ (regeneration uses the model, but logic/flows are testable with fakes). Needs Mac: ❌.

### W2 — Missed-finding wizard *(point 2.7; captures false negatives)*
**Goal:** teach "you should have caught this" — the one thing accept/reject can't.
- Wizard: paste the finding text + pick the dataset it came from.
- Model analyses the dataset + the pasted finding → determines **why it was missed**
  → creates the structured finding (`source = analyst_added`) → emits a
  **why-missed + lessons** summary → operator can add feedback on that summary.
- Feeds RAG (miss-pattern lessons) + exporter (positives the model originally missed).
- Requires the dataset to still be present.
- Testable here: ✅ (orchestration with fakes). Needs Mac: ❌ for logic, model run on box.

### W3 — Training Hunts *(point 3; the foundational corpus + best eval set)*
**Goal:** turn years of historic hunts into the cold-start corpus and the eval baseline.
- **Training Hunt** = `Hunt.kind = training` — tenant-scoped, never live findings.
- **Ingestion wizard:** upload methodology + datasets + the known findings/report.
  Old findings live as prose → a **model-assisted importer proposes structured
  findings**, the operator **confirms** (quality gate, avoids teaching misparses).
- **Coverage-aware:**
  - Full hunt (methodology + datasets + findings) → trains the whole pipeline incl. analysis.
  - Report-only (datasets gone) → trains methodology structure, writing, and report format only.
- **Dual feed:** training corpus (gold positives across stages) **and** the golden
  eval set (replaces/augments synthetic + holdout in `eval_runner`).
- Optional: weight recent hunts higher / exclude stale formats (learn the *current* standard).
- Testable here: ✅ ingestion/alignment logic; model-assisted extract runs on box.
- This is large — likely its own 1–2 sessions.

### W4 — All-stages learning + learning summaries *(point 2.5, 2.6)*
**Goal:** the same disposition+feedback+score primitive at every AI stage.
- Stages: **methodology comprehension, analysis plan, correlation, QA, finding
  writing** (surface writing as its own reviewable step — flagged as not-yet-built).
- Each stage output becomes a feedback target (`LearningEvent.target_type`), with the
  same Reject/Accept/Partial/Score + feedback controls.
- Per-stage RAG context + per-stage training corpora (each stage = a distinct
  example shape).
- **Learning summary** rendered at the bottom of each stage's normal summary —
  grounded in the actual dispositions/feedback for that stage (no invented lessons).
- Sequenced *after* W1 proves the primitive; methodology/plan accumulate slowly
  (once per hunt), so prioritise analysis/correlation/QA first.
- Large — likely split per stage.

### W5 — Anonymisation layer *(optional quality lever, not safety)*
**Goal:** make the model learn *patterns*, not memorise its own hostnames.
- Entity-aware scrubbing → consistent placeholders (`HOST_1`, `USER_1`, `IP_1`)
  across all fields of a training example, using the finding's known entities.
- Toggle per export. With per-client isolation this is **quality**, not isolation
  safety — so it can ship late or be skipped.
- Testable here: ✅ fully (pure text transform).

### W6 — MLX trainer CLI *(needs base-model decision + runs on the Mac)*
**Goal:** the one piece that actually trains weights.
- `lense train <client>`: assemble corpus (W1–W4 signals + W3 hunts) → **MLX-LM
  LoRA** → fuse → GGUF → `ollama create lens-tenant-<id>:<ver>` → `POST /models/register`.
- Then: operator runs **Evaluate** (existing gate) → **Promote** if it beats baseline.
- Base model: a **Western-origin ~8B** (decision pending). `Modelfile` template + run docs.
- Testable here: ❌ (Apple-Silicon + MLX only). I write it; you execute and validate.

### W7 — Preference-tuning upgrade *(later, optional)*
**Goal:** use the scores + accepted-vs-rejected + partial before/after as **DPO
preference pairs**, beyond plain imitation (SFT).
- Heavier; only if SFT + RAG leave quality on the table. Pure backlog.

---

## 4. Dependencies

```
W0 ──┬─► W1 ──► W2
     │    └────► W4
     ├─► W3 ───► (feeds eval + corpus)
     ├─► W5 (independent)
     └─► W6 (needs W1/W3 corpus + base model) ──► W7
```

W0 unblocks everything. W1 proves the primitive that W2/W4 reuse. W3 is parallel
and independently valuable (it also upgrades the eval set). W6 is last and is the
only Mac-bound, decision-gated piece.

## 5. Recommended session sequence

| Session | Workstream | Value the day it ships | Mac needed? |
|---|---|---|---|
| 1 | W0 foundations | Spine + isolation guarantees locked | No |
| 2 | W1 finding disposition loop | Better findings next hunt **via RAG**, no trainer needed | No |
| 3 | W2 missed-finding wizard | False-negative capture | No |
| 4–5 | W3 Training Hunts | Cold-start corpus + far better eval baseline | No (model-assist runs on box) |
| 6–7 | W4 all-stages + summaries | Whole pipeline learns; per-stage summaries | No |
| 8 | W5 anonymisation | Skill-over-memorisation polish | No |
| 9 | W6 MLX trainer | First actual per-client trained model | **Yes** + base-model pick |
| later | W7 preference tuning | Marginal quality | Yes |

Note: **Sessions 1–8 need no Mac and no base-model decision** — they build all the
data, signal, corpus, eval, and isolation. Only Session 9 (W6) needs your
Apple-Silicon box and the base-model choice. So we can build ~90% of this now, and
the day you pick the base model the trainer drops into a fully-prepared loop.

## 6. Immediate value before any training exists

Because every signal also writes to RAG, the operator sees improvement from
Session 2 onward **without a single fine-tune** — feedback, corrections,
missed-findings, and historic hunts all become retrievable context immediately.
Fine-tuning (W6) then compounds it.

## 7. Open decisions (none block Sessions 1–8)

- **Base model** for W6 (Western-origin ~8B) — needed only at Session 9.
- **Accept-feedback required or optional?** (recommend optional; reject/partial required.)
- **Anonymisation on by default?** (recommend off initially; per-client isolation already covers safety.)
- **Format-drift handling** in Training Hunts (weight recent vs let operator exclude).
