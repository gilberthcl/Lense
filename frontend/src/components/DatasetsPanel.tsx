import { useEffect, useRef, useState } from "react";
import { api, ApiError, pollJob } from "../lib/api";
import type { Dataset, Job } from "../lib/types";
import { useToast } from "./Toast";
import {
  Button,
  Card,
  DatasetStatusBadge,
  EmptyState,
  fmtBytes,
  fmtDate,
  PanelHeader,
  Spinner,
} from "./ui";

const MAX_BYTES = 20 * 1024 * 1024; // 20MB client-side cap

interface ActiveJob {
  datasetId: string;
  job: Job;
}

export default function DatasetsPanel({
  tid,
  hid,
  onAnalysisComplete,
}: {
  tid: string;
  hid: string;
  onAnalysisComplete: () => void;
}) {
  const toast = useToast();
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [active, setActive] = useState<ActiveJob | null>(null);
  const [runningAll, setRunningAll] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

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

  const onUpload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      toast.error("Only .csv files are supported.");
      return;
    }
    if (file.size > MAX_BYTES) {
      toast.error(`File too large (${fmtBytes(file.size)}). Max is 20MB.`);
      return;
    }
    setUploading(true);
    try {
      await api.uploadDataset(tid, hid, file);
      toast.success(`Uploaded ${file.name}.`);
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  // Run analysis for one dataset, polling its job to completion.
  const runAnalysis = async (ds: Dataset): Promise<boolean> => {
    try {
      const job = await api.analyzeDataset(tid, hid, ds.id);
      setActive({ datasetId: ds.id, job });
      const final = await pollJob(tid, hid, job.id, (j) =>
        setActive({ datasetId: ds.id, job: j }),
      );
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
    const pending = (datasets ?? []).filter(
      (d) => d.status === "uploaded" || d.status === "error",
    );
    if (pending.length === 0) {
      toast.info("No datasets pending analysis.");
      return;
    }
    setRunningAll(true);
    let any = false;
    // Sequential — one at a time as required.
    for (const ds of pending) {
      const ok = await runAnalysis(ds);
      any = any || ok;
      await load();
    }
    setRunningAll(false);
    if (any) onAnalysisComplete();
  };

  const busy = uploading || runningAll || active !== null;
  const pendingCount = (datasets ?? []).filter(
    (d) => d.status === "uploaded" || d.status === "error",
  ).length;

  return (
    <Card>
      <PanelHeader
        title="Datasets"
        subtitle="CSV evidence (max 20MB) — analyzed against the tenant constitution"
        right={
          <div className="flex items-center gap-2">
            <Button
              variant="success"
              disabled={busy || pendingCount === 0}
              onClick={onAnalyzeAll}
            >
              {runningAll ? <Spinner /> : `Analyze all (${pendingCount})`}
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onUpload(f);
              }}
            />
            <Button
              variant="primary"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              {uploading ? <Spinner /> : "Upload CSV"}
            </Button>
          </div>
        }
      />

      {active && (
        <div className="border-b border-slate-800 bg-slate-950/40 px-4 py-3">
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <span className="text-slate-300">
              {active.job.current_task ?? active.job.phase ?? "Analyzing…"}
            </span>
            <span className="font-mono text-slate-500">
              {Math.round(active.job.progress ?? 0)}%
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800">
            <div
              className="h-full bg-indigo-500 transition-all duration-300"
              style={{ width: `${Math.max(2, active.job.progress ?? 0)}%` }}
            />
          </div>
        </div>
      )}

      <div className="p-4">
        {datasets === null ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : datasets.length === 0 ? (
          <EmptyState>No datasets uploaded yet. Upload a CSV to begin.</EmptyState>
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
                  <th className="px-3 py-2 font-medium">Uploaded</th>
                  <th className="py-2 pl-3 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((ds) => {
                  const isActive = active?.datasetId === ds.id;
                  const canAnalyze =
                    ds.status === "uploaded" || ds.status === "error";
                  return (
                    <tr
                      key={ds.id}
                      className="border-b border-slate-900 last:border-0"
                    >
                      <td className="py-2.5 pr-3 font-mono text-xs text-slate-200">
                        {ds.filename}
                      </td>
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
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-slate-400">
                        {ds.col_count ?? "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-slate-400">
                        {fmtBytes(ds.file_size)}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-slate-500">
                        {fmtDate(ds.created_at)}
                      </td>
                      <td className="py-2.5 pl-3 text-right">
                        <Button
                          className="px-2 py-1 text-xs"
                          disabled={busy || !canAnalyze}
                          onClick={() => onAnalyzeOne(ds)}
                        >
                          {canAnalyze ? "Analyze" : "—"}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}
