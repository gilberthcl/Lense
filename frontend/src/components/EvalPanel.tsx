import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { EvalBaseline } from "../lib/types";
import { useToast } from "./Toast";
import { Badge, Button, Card, PanelHeader, Spinner } from "./ui";

/**
 * Golden-eval baseline (LoRA fine-tuning, Phase 2).
 *
 * Runs a fixed set of golden cases (committed synthetic + optional per-tenant
 * holdout) through the CURRENT model and records precision/recall, hallucination
 * rate, and parse-error rate. This is the line a future fine-tuned model must not
 * fall below. The run hits the local model, so it executes in the background and
 * we poll the baseline file for its status.
 */
export default function EvalPanel({ tid }: { tid: string }) {
  const toast = useToast();
  const [data, setData] = useState<EvalBaseline | null>(null);
  const [holdout, setHoldout] = useState(false);
  const [starting, setStarting] = useState(false);
  const timer = useRef<number | null>(null);

  const load = () =>
    api.getEvalBaseline(tid).then(setData).catch((e: ApiError) => toast.error(e.message));

  useEffect(() => {
    load();
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  // Poll while a run is in flight.
  useEffect(() => {
    if (data?.status === "running" && !timer.current) {
      timer.current = window.setInterval(load, 2500);
    } else if (data?.status !== "running" && timer.current) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.status]);

  const run = async () => {
    setStarting(true);
    try {
      await api.runEval(tid, holdout);
      toast.success("Eval started — running the current model over the golden set.");
      await load();
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setStarting(false);
    }
  };

  const m = data?.metrics;
  const running = data?.status === "running";

  return (
    <Card className="mt-4">
      <PanelHeader
        title="Model quality baseline"
        subtitle="Scores the current model on a golden set — the bar a future fine-tuned model must beat"
        right={
          <div className="flex items-center gap-3">
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={holdout}
                onChange={(e) => setHoldout(e.target.checked)}
                disabled={running}
                className="h-3.5 w-3.5 accent-indigo-500"
              />
              Include holdout
            </label>
            <Button onClick={run} disabled={starting || running}>
              {starting || running ? <Spinner /> : "Run baseline eval"}
            </Button>
          </div>
        }
      />
      <div className="p-4">
        {!data || data.status === "none" ? (
          <p className="text-sm text-slate-500">
            No baseline yet. Run it to measure the current model on the golden set (a couple of
            synthetic cases, plus this client's validated findings if you include the holdout).
          </p>
        ) : running ? (
          <div className="flex items-center gap-2 text-sm text-indigo-300">
            <Spinner /> Running the model over the golden set… this can take a few minutes.
          </div>
        ) : data.status === "error" ? (
          <div className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 font-mono text-[11px] text-red-300">
            {data.error ?? "Eval failed."}
          </div>
        ) : m ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
              <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
                model: {data.model ?? "—"}
              </Badge>
              <span>
                {data.sources?.synthetic ?? 0} synthetic · {data.sources?.holdout ?? 0} holdout ·{" "}
                {m.cases} case(s)
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <Metric label="Precision" value={m.precision} good="high" />
              <Metric label="Recall" value={m.recall} good="high" />
              <Metric label="F1" value={m.f1} good="high" />
              <Metric label="Hallucination" value={m.hallucination_rate} good="low" />
              <Metric label="Parse errors" value={m.parse_error_rate} good="low" />
            </div>

            <p className="text-[11px] text-slate-500">
              TP {m.tp} · FP {m.fp} · FN {m.fn} · {m.findings_produced} finding(s) produced.
              Precision/hallucination guard against a model that over-reports; recall guards against
              one that misses. A future tuned model is compared against these numbers before it can
              go live.
            </p>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function Metric({ label, value, good }: { label: string; value: number; good: "high" | "low" }) {
  // Color by whether the value is favorable: high-is-good (precision) vs low-is-good (errors).
  const pct = Math.round(value * 100);
  const favorable = good === "high" ? value >= 0.8 : value <= 0.05;
  const tone = favorable ? "text-emerald-300" : good === "high" ? "text-amber-300" : "text-rose-300";
  return (
    <div className="rounded border border-slate-800 bg-slate-950/40 px-3 py-2">
      <div className={`text-xl font-semibold ${tone}`}>{pct}%</div>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}
