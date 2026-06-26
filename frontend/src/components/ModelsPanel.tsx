import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { TenantModelInfo, TenantModelsList } from "../lib/types";
import { useToast } from "./Toast";
import BaseModelSelect from "./BaseModelSelect";
import { Badge, Button, Card, PanelHeader, Spinner } from "./ui";

/**
 * Per-tenant fine-tuned model registry (LoRA fine-tuning, Phase 3).
 *
 * Inert until the (offline) trainer registers a candidate: with nothing active,
 * the pipeline keeps using the global model. Once candidates exist, this lets an
 * operator evaluate them against the golden baseline and promote one — promotion
 * is blocked server-side if the candidate regressed.
 */
const STATUS_STYLE: Record<string, string> = {
  active: "border border-emerald-800 bg-emerald-950 text-emerald-300",
  validating: "border border-amber-800 bg-amber-950 text-amber-300",
  rejected: "border border-rose-900 bg-rose-950 text-rose-300",
  retired: "border border-slate-700 bg-slate-800 text-slate-400",
  draft: "border border-slate-700 bg-slate-800 text-slate-400",
};

export default function ModelsPanel({ tid }: { tid: string }) {
  const toast = useToast();
  const [data, setData] = useState<TenantModelsList | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = () =>
    api.getTenantModels(tid).then(setData).catch((e: ApiError) => toast.error(e.message));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  const act = async (id: number, fn: () => Promise<unknown>, ok: string) => {
    setBusy(id);
    try {
      await fn();
      toast.success(ok);
      await load();
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="mt-4">
      <PanelHeader
        title="Fine-tuned model"
        subtitle="Per-client LoRA models. Routing stays on the global model until one is promoted."
        right={
          <Badge
            className={
              data?.active_model
                ? "border border-emerald-800 bg-emerald-950 text-emerald-300"
                : "border border-slate-700 bg-slate-800 text-slate-400"
            }
          >
            {data?.active_model ? `active: ${data.active_model}` : "global model (default)"}
          </Badge>
        }
      />
      <div className="p-4">
        <div className="mb-4 rounded border border-slate-800 bg-slate-950/40 p-3">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Base model</p>
          <BaseModelSelect tid={tid} />
        </div>
        {!data ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : data.models.length === 0 ? (
          <p className="text-sm text-slate-500">
            No fine-tuned models yet. The offline trainer (<code>lense train</code>, not yet
            enabled) registers candidates here once a base model is chosen. Until then, analysis
            uses the global model — nothing to do.
          </p>
        ) : (
          <div className="space-y-2">
            {data.models.map((m) => (
              <ModelRow key={m.id} tid={tid} m={m} busy={busy === m.id} act={act} />
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

function ModelRow({
  tid,
  m,
  busy,
  act,
}: {
  tid: string;
  m: TenantModelInfo;
  busy: boolean;
  act: (id: number, fn: () => Promise<unknown>, ok: string) => void;
}) {
  const regressed = m.comparison?.regressed;
  const evaluated = !!m.eval_metrics && regressed !== null && regressed !== undefined;
  const canPromote = evaluated && regressed === false && m.status !== "active";

  return (
    <div className="rounded border border-slate-800 bg-slate-950/40 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-indigo-300">v{m.version}</span>
        <span className="font-mono text-xs text-slate-300">{m.ollama_model_name}</span>
        <span className="text-[11px] text-slate-500">base: {m.base_model}</span>
        <Badge className={STATUS_STYLE[m.status] ?? STATUS_STYLE.draft}>{m.status}</Badge>
        {evaluated && (
          <Badge
            className={
              regressed
                ? "border border-rose-900 bg-rose-950 text-rose-300"
                : "border border-emerald-800 bg-emerald-950 text-emerald-300"
            }
          >
            {regressed ? "regressed vs baseline" : "passes baseline"}
          </Badge>
        )}
      </div>

      {m.eval_metrics && (
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-slate-400">
          <span>P {Math.round(m.eval_metrics.precision * 100)}%</span>
          <span>R {Math.round(m.eval_metrics.recall * 100)}%</span>
          <span>F1 {Math.round(m.eval_metrics.f1 * 100)}%</span>
          <span>halluc {Math.round(m.eval_metrics.hallucination_rate * 100)}%</span>
          <span>parse-err {Math.round(m.eval_metrics.parse_error_rate * 100)}%</span>
        </div>
      )}

      {m.status !== "active" && m.status !== "rejected" && (
        <div className="mt-2 flex gap-1.5">
          <Button
            variant="ghost"
            className="px-2 py-1 text-xs"
            disabled={busy}
            onClick={() => act(m.id, () => api.evaluateModel(tid, m.id, false), "Evaluation started.")}
          >
            {busy ? <Spinner /> : "Evaluate"}
          </Button>
          <Button
            className="px-2 py-1 text-xs"
            disabled={busy || !canPromote}
            title={canPromote ? "" : "Must pass a golden-eval vs the baseline first"}
            onClick={() => act(m.id, () => api.promoteModel(tid, m.id), "Model promoted.")}
          >
            Promote
          </Button>
          <Button
            variant="ghost"
            className="px-2 py-1 text-xs"
            disabled={busy}
            onClick={() => act(m.id, () => api.rejectModel(tid, m.id), "Model rejected.")}
          >
            Reject
          </Button>
        </div>
      )}
    </div>
  );
}
