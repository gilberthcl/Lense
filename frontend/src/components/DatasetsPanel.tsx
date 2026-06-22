import { Fragment, useEffect, useRef, useState } from "react";
import { api, ApiError, pollJob } from "../lib/api";
import type { Dataset, DatasetPreview, Hunt, Job } from "../lib/types";
import { useToast } from "./Toast";
import {
  Badge,
  Button,
  Card,
  DatasetStatusBadge,
  EmptyState,
  fmtBytes,
  PanelHeader,
  Spinner,
} from "./ui";

const MAX_BYTES = 20 * 1024 * 1024; // 20MB client-side cap

interface ActiveJob {
  datasetId: string;
  job: Job;
}

const LEVEL_COLOR: Record<string, string> = {
  high: "border border-red-800 bg-red-950 text-red-300",
  medium: "border border-amber-800 bg-amber-950 text-amber-300",
  low: "border border-emerald-800 bg-emerald-950 text-emerald-300",
};

export default function DatasetsPanel({
  tid,
  hid,
  hunt,
  onHuntRefresh,
  onAnalysisComplete,
}: {
  tid: string;
  hid: string;
  hunt: Hunt | null;
  onHuntRefresh: () => void;
  onAnalysisComplete: () => void;
}) {
  const toast = useToast();
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [active, setActive] = useState<ActiveJob | null>(null);
  const [runningAll, setRunningAll] = useState(false);
  const [planJob, setPlanJob] = useState<Job | null>(null);
  const [planning, setPlanning] = useState(false);
  const [showPlan, setShowPlan] = useState(true);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const plan = hunt?.analysis_plan ?? null;

  const load = () =>
    api
      .listDatasets(tid, hid)
      .then(setDatasets)
      .catch((e: ApiError) => {
        toast.error(e.message);
        setDatasets([]);
      });

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid, hid]);

  // Upload one or many files, sequentially.
  const onUploadMany = async (files: FileList) => {
    const list = Array.from(files);
    setUploading(true);
    let okCount = 0;
    for (const file of list) {
      if (!file.name.toLowerCase().endsWith(".csv")) {
        toast.error(`Skipped ${file.name}: only .csv is supported.`);
        continue;
      }
      if (file.size > MAX_BYTES) {
        toast.error(`Skipped ${file.name}: larger than 20MB.`);
        continue;
      }
      try {
        await api.uploadDataset(tid, hid, file);
        okCount += 1;
      } catch (e) {
        toast.error(`${file.name}: ${e instanceof ApiError ? e.message : "upload failed"}`);
      }
    }
    if (fileRef.current) fileRef.current.value = "";
    if (okCount) toast.success(`Uploaded ${okCount} file${okCount > 1 ? "s" : ""}.`);
    setUploading(false);
    await load();
  };

  const runAnalysis = async (ds: Dataset): Promise<boolean> => {
    try {
      const job = await api.analyzeDataset(tid, hid, ds.id);
      setActive({ datasetId: ds.id, job });
      const final = await pollJob(tid, hid, job.id, (j) => setActive({ datasetId: ds.id, job: j }));
      if (final.status === "error") {
        toast.error(`Analysis failed: ${final.error ?? "unknown error"}`);
        return false;
      }
      toast.success(`Analysis complete for ${ds.filename}.`);
      return true;
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Analysis failed.");
      return false;
    } finally {
      setActive(null);
    }
  };

  const onAnalyzeOne = async (ds: Dataset) => {
    const ok = await runAnalysis(ds);
    await load();
    if (ok) onAnalysisComplete();
  };

  const onAnalyzeAll = async () => {
    const pending = (datasets ?? []).filter((d) => d.status === "uploaded" || d.status === "error");
    if (pending.length === 0) {
      toast.info("No datasets pending analysis.");
      return;
    }
    setRunningAll(true);
    let any = false;
    for (const ds of pending) {
      const ok = await runAnalysis(ds);
      any = any || ok;
      await load();
    }
    setRunningAll(false);
    if (any) onAnalysisComplete();
  };

  const runPlan = async () => {
    setPlanning(true);
    setPlanJob({ id: "", status: "queued", progress: 0 });
    try {
      const started = await api.analysisPlan(tid, hid);
      const final = await pollJob(tid, hid, started.id, (j) => setPlanJob(j));
      if (final.status === "error") toast.error("Planning failed — see the log.");
      else {
        toast.success("Analysis plan ready.");
        onHuntRefresh();
        setShowPlan(true);
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Planning failed.");
    } finally {
      setPlanning(false);
    }
  };

  const togglePreview = async (ds: Dataset) => {
    if (previewId === ds.id) {
      setPreviewId(null);
      setPreview(null);
      return;
    }
    setPreviewId(ds.id);
    setPreview(null);
    setPreviewLoading(true);
    try {
      setPreview(await api.previewDataset(tid, hid, ds.id));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Preview failed.");
      setPreviewId(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const busy = uploading || runningAll || active !== null;
  const pendingCount = (datasets ?? []).filter((d) => d.status === "uploaded" || d.status === "error").length;
  const hasDatasets = (datasets?.length ?? 0) > 0;

  return (
    <div className="space-y-4">
      {/* Analysis plan */}
      <Card>
        <PanelHeader
          title="Analysis Plan"
          subtitle="The model plans phases, batches & QA from dataset metadata — before any contents are analyzed"
          right={
            <Button variant={plan ? "ghost" : "primary"} onClick={runPlan} disabled={planning || !hasDatasets}>
              {planning ? (
                <>
                  <Spinner /> {planJob?.progress ?? 0}%
                </>
              ) : plan ? (
                "Re-plan"
              ) : (
                "Plan analysis"
              )}
            </Button>
          }
        />
        <div className="p-4">
          {(planning || planJob) && (
            <div className="mb-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="text-slate-300">
                  {planJob?.status === "error" ? "Planning failed" : planJob?.current_task ?? "Starting…"}
                </span>
                <span className="font-mono text-slate-500">
                  {planJob?.model ? `model: ${planJob.model}` : ""} {planJob?.progress != null ? `· ${planJob.progress}%` : ""}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800">
                <div className="h-full bg-indigo-500 transition-all" style={{ width: `${Math.max(3, planJob?.progress ?? 0)}%` }} />
              </div>
              {!!planJob?.log?.length && (
                <div className="mt-2 max-h-32 overflow-y-auto rounded bg-black/30 p-2 font-mono text-[11px] text-slate-400">
                  {planJob.log.map((l, i) => (
                    <div key={i}>
                      <span className="text-slate-600">{l.at.toFixed(1)}s</span> · {l.msg}
                    </div>
                  ))}
                </div>
              )}
              {planJob?.status === "error" && planJob.error && (
                <p className="mt-2 text-xs text-red-400">{planJob.error}</p>
              )}
            </div>
          )}

          {!plan ? (
            <EmptyState>
              {hasDatasets
                ? "No plan yet. Click “Plan analysis” to have the model stage the work."
                : "Upload datasets first, then plan the analysis."}
            </EmptyState>
          ) : (
            <PlanView plan={plan} expanded={showPlan} onToggle={() => setShowPlan((s) => !s)} />
          )}
        </div>
      </Card>

      {/* Datasets */}
      <Card>
        <PanelHeader
          title="Datasets"
          subtitle="CSV evidence (max 20MB each) — analyzed against the methodology & client context"
          right={
            <div className="flex items-center gap-2">
              <Button variant="success" disabled={busy || pendingCount === 0} onClick={onAnalyzeAll}>
                {runningAll ? <Spinner /> : `Analyze all (${pendingCount})`}
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,text/csv"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) onUploadMany(e.target.files);
                }}
              />
              <Button variant="primary" disabled={busy} onClick={() => fileRef.current?.click()}>
                {uploading ? <Spinner /> : "Upload CSV(s)"}
              </Button>
            </div>
          }
        />

        {active && (
          <div className="border-b border-slate-800 bg-slate-950/40 px-4 py-3">
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="text-slate-300">{active.job.current_task ?? "Analyzing…"}</span>
              <span className="font-mono text-slate-500">{Math.round(active.job.progress ?? 0)}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800">
              <div className="h-full bg-indigo-500 transition-all duration-300" style={{ width: `${Math.max(2, active.job.progress ?? 0)}%` }} />
            </div>
          </div>
        )}

        <div className="p-4">
          {datasets === null ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner /> Loading…
            </div>
          ) : datasets.length === 0 ? (
            <EmptyState>No datasets uploaded yet. Upload one or more CSVs to begin.</EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="py-2 pr-3 font-medium">Filename</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 text-right font-medium">Rows</th>
                    <th className="px-3 py-2 text-right font-medium">Cols</th>
                    <th className="px-3 py-2 text-right font-medium">Size</th>
                    <th className="py-2 pl-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.map((ds) => {
                    const isActive = active?.datasetId === ds.id;
                    const canAnalyze = ds.status === "uploaded" || ds.status === "error";
                    const isPreview = previewId === ds.id;
                    return (
                      <Fragment key={ds.id}>
                        <tr className="border-b border-slate-900 last:border-0">
                          <td className="py-2.5 pr-3 font-mono text-xs text-slate-200">{ds.filename}</td>
                          <td className="px-3 py-2.5">
                            {isActive ? (
                              <span className="inline-flex items-center gap-1.5 text-xs text-indigo-300">
                                <Spinner className="h-3 w-3" /> analyzing
                              </span>
                            ) : (
                              <DatasetStatusBadge status={ds.status} />
                            )}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono text-xs text-slate-400">
                            {ds.row_count?.toLocaleString() ?? "—"}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono text-xs text-slate-400">{ds.col_count || "—"}</td>
                          <td className="px-3 py-2.5 text-right font-mono text-xs text-slate-400">{fmtBytes(ds.file_size)}</td>
                          <td className="py-2.5 pl-3 text-right">
                            <div className="inline-flex gap-1.5">
                              <Button className="px-2 py-1 text-xs" variant="ghost" onClick={() => togglePreview(ds)}>
                                {isPreview ? "Hide" : "Preview"}
                              </Button>
                              <Button className="px-2 py-1 text-xs" disabled={busy || !canAnalyze} onClick={() => onAnalyzeOne(ds)}>
                                {canAnalyze ? "Analyze" : "—"}
                              </Button>
                            </div>
                          </td>
                        </tr>
                        {isPreview && (
                          <tr>
                            <td colSpan={6} className="bg-slate-950/50 px-3 py-3">
                              {previewLoading || !preview ? (
                                <div className="flex items-center gap-2 text-xs text-slate-500">
                                  <Spinner className="h-3 w-3" /> loading preview…
                                </div>
                              ) : (
                                <PreviewTable data={preview} />
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

function PreviewTable({ data }: { data: DatasetPreview }) {
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">
        {data.row_count.toLocaleString()} rows · {data.col_count} columns · showing first {data.rows.length}
      </p>
      <div className="max-h-72 overflow-auto rounded border border-slate-800">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-900">
            <tr>
              {data.columns.map((c, i) => (
                <th key={i} className="whitespace-nowrap px-2 py-1.5 text-left font-mono font-medium text-slate-400">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {data.rows.map((row, i) => (
              <tr key={i}>
                {row.map((v, j) => (
                  <td key={j} className="max-w-xs truncate px-2 py-1 font-mono text-slate-300" title={v}>
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PlanView({
  plan,
  expanded,
  onToggle,
}: {
  plan: NonNullable<Hunt["analysis_plan"]>;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="space-y-4">
      {plan.summary && <p className="text-sm leading-relaxed text-slate-300">{plan.summary}</p>}
      <div className="flex flex-wrap gap-2 text-xs">
        {plan.estimated_rounds != null && (
          <Badge className="border border-indigo-800 bg-indigo-950 text-indigo-300">
            {plan.estimated_rounds} round{plan.estimated_rounds === 1 ? "" : "s"}
          </Badge>
        )}
        {!!plan.phases?.length && (
          <Badge className="border border-slate-700 bg-slate-800 text-slate-300">{plan.phases.length} phases</Badge>
        )}
        <button onClick={onToggle} className="text-indigo-400 hover:text-indigo-300">
          {expanded ? "Hide details" : "Show details"}
        </button>
      </div>

      {expanded && (
        <>
          {!!plan.phases?.length && (
            <ol className="space-y-2">
              {plan.phases.map((p, i) => (
                <li key={i} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                  <p className="text-sm font-medium text-slate-200">
                    <span className="font-mono text-slate-500">{i + 1}. </span>
                    {p.name}
                  </p>
                  {p.focus && <p className="mt-1 text-xs text-slate-400">{p.focus}</p>}
                  {!!p.datasets?.length && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {p.datasets.map((d, j) => (
                        <span key={j} className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-300">
                          {d}
                        </span>
                      ))}
                    </div>
                  )}
                  {p.rationale && <p className="mt-1.5 text-xs italic text-slate-500">{p.rationale}</p>}
                </li>
              ))}
            </ol>
          )}

          {!!plan.complexity?.length && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Complexity</p>
              <ul className="space-y-1">
                {plan.complexity.map((c, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                    <Badge className={`shrink-0 ${LEVEL_COLOR[c.level] ?? LEVEL_COLOR.medium}`}>{c.level}</Badge>
                    <span className="min-w-0">
                      <span className="font-mono text-xs text-slate-400">{c.dataset}</span>
                      {c.reason ? ` — ${c.reason}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {plan.batching && (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Batching</p>
              <p className="text-sm text-slate-300">{plan.batching}</p>
            </div>
          )}
          {plan.qa_plan && (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">QA plan</p>
              <p className="text-sm text-slate-300">{plan.qa_plan}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
