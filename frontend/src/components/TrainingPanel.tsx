import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { TrainingStats } from "../lib/types";
import { useToast } from "./Toast";
import { Badge, Button, Card, PanelHeader, Spinner } from "./ui";

/**
 * Per-tenant training-data inspection + export (LoRA fine-tuning, Phase 1).
 *
 * Shows how much trainable signal this client has accumulated and lets the
 * operator export it as JSONL. This does NOT train a model — it produces the
 * dataset a future offline trainer would consume. See
 * docs/per-tenant-lora-finetuning.md.
 */
export default function TrainingPanel({ tid }: { tid: string }) {
  const toast = useToast();
  const [stats, setStats] = useState<TrainingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .getTrainingStats(tid)
      .then(setStats)
      .catch((e: ApiError) => toast.error(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  const onExport = async () => {
    setExporting(true);
    try {
      const r = await api.exportTrainingSet(tid);
      setStats(r);
      toast.success(
        `Exported ${r.written?.sft_examples ?? 0} training + ${r.written?.negative_examples ?? 0} negative example(s).`,
      );
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setExporting(false);
    }
  };

  const cats = stats ? Object.entries(stats.by_category).sort((a, b) => b[1] - a[1]) : [];

  return (
    <Card className="mt-4">
      <PanelHeader
        title="Model training data"
        subtitle="Validated findings become fine-tuning examples for a future per-client model — see docs/per-tenant-lora-finetuning.md"
        right={
          <Button onClick={onExport} disabled={exporting || loading}>
            {exporting ? <Spinner /> : "Export training set"}
          </Button>
        }
      />
      <div className="p-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : !stats ? (
          <p className="text-sm text-slate-500">No data.</p>
        ) : (
          <div className="space-y-4">
            {/* Readiness */}
            <div className="flex flex-wrap items-center gap-3">
              <Badge
                className={
                  stats.ready_for_training
                    ? "border border-emerald-800 bg-emerald-950 text-emerald-300"
                    : "border border-amber-800 bg-amber-950 text-amber-300"
                }
              >
                {stats.ready_for_training ? "✓ Ready to train" : "Not enough data yet"}
              </Badge>
              <span className="text-sm text-slate-400">
                {stats.eligible_positives} / {stats.min_validated} eligible validated findings
              </span>
            </div>

            {/* Counts */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Validated" value={stats.validated} tone="emerald" />
              <Stat label="Eligible positives" value={stats.eligible_positives} tone="indigo" />
              <Stat label="Rejected (negatives)" value={stats.rejected} tone="rose" />
              <Stat label="Thin / skipped" value={stats.thin_validated_skipped} tone="slate" />
            </div>

            {/* Category mix */}
            {cats.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Positive examples by category
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {cats.map(([c, n]) => (
                    <Badge key={c} className="border border-slate-700 bg-slate-800 text-slate-300">
                      {c}: {n}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Last export */}
            {stats.written && (
              <div className="rounded border border-slate-800 bg-slate-950/40 p-3 text-xs text-slate-400">
                <p className="mb-1 font-semibold text-slate-300">Last export</p>
                <p className="font-mono">{stats.written.sft_path}</p>
                <p className="font-mono">{stats.written.negatives_path}</p>
              </div>
            )}

            <p className="text-[11px] leading-relaxed text-slate-500">
              Validated findings train the model to reproduce good findings; rejected ones teach
              it to suppress false positives. A tune only runs once you clear the minimum
              ({stats.min_validated}) — too few examples overfit and degrade the model. Exported
              files stay on-box and are never committed. Training itself is a separate, offline,
              operator-gated step (not yet enabled).
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}

const TONE: Record<string, string> = {
  emerald: "text-emerald-300",
  indigo: "text-indigo-300",
  rose: "text-rose-300",
  slate: "text-slate-300",
};

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950/40 px-3 py-2">
      <div className={`text-xl font-semibold ${TONE[tone] ?? "text-slate-300"}`}>{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}
