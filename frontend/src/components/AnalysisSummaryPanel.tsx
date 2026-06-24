import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { AnalysisSummary } from "../lib/types";
import { useToast } from "./Toast";
import { Button, Card, CategoryBadge, EmptyState, PanelHeader, Spinner } from "./ui";

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950/40 px-3 py-2">
      <div className="text-lg font-semibold text-slate-100">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}

export default function AnalysisSummaryPanel({
  tid,
  hid,
  reloadKey,
}: {
  tid: string;
  hid: string;
  reloadKey: number;
}) {
  const toast = useToast();
  const [data, setData] = useState<AnalysisSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .getAnalysisSummary(tid, hid)
      .then(setData)
      .catch((e: ApiError) => toast.error(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid, hid, reloadKey]);

  const totals = data?.totals;

  return (
    <Card>
      <PanelHeader
        title="Analysis summary"
        subtitle="What the analysis phase did — totals and per-dataset observations"
        right={
          <Button variant="ghost" onClick={load} disabled={loading}>
            {loading ? <Spinner /> : "Refresh"}
          </Button>
        }
      />
      <div className="space-y-4 p-4">
        {data === null ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : (
          <>
            {/* Totals */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Datasets analyzed" value={`${totals?.analyzed ?? 0}/${totals?.datasets ?? 0}`} />
              <Stat label="Findings" value={totals?.active_findings ?? 0} />
              <Stat label="Categories" value={Object.keys(totals?.by_category ?? {}).length} />
              <Stat label="High/Critical" value={(totals?.by_severity?.high ?? 0) + (totals?.by_severity?.critical ?? 0)} />
            </div>

            {/* Category / severity breakdown */}
            {totals && (Object.keys(totals.by_category).length > 0 || Object.keys(totals.by_severity).length > 0) && (
              <div className="flex flex-wrap gap-4 text-xs text-slate-400">
                {Object.entries(totals.by_category).map(([k, v]) => (
                  <span key={k} className="flex items-center gap-1.5">
                    <CategoryBadge category={k} /> {v}
                  </span>
                ))}
                {Object.entries(totals.by_severity).map(([k, v]) => (
                  <span key={k} className="font-mono">
                    {k}: {v}
                  </span>
                ))}
              </div>
            )}

            {/* Per-dataset observations */}
            {data.datasets.length === 0 ? (
              <EmptyState>No datasets in this hunt yet.</EmptyState>
            ) : (
              <div className="space-y-3">
                {data.datasets.map((d) => (
                  <div key={d.id} className="rounded border border-slate-800 bg-slate-950/40 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="break-all text-sm font-medium text-slate-200">{d.filename}</span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[11px] ${
                          d.status === "analyzed"
                            ? "bg-emerald-900/50 text-emerald-300"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {d.status}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {d.row_count ?? 0} rows · {d.finding_count} finding(s)
                      </span>
                    </div>

                    {d.assessment ? (
                      <p className="mt-2 text-sm leading-relaxed text-slate-300">{d.assessment}</p>
                    ) : (
                      <p className="mt-2 text-xs italic text-slate-600">
                        No assessment recorded for this dataset.
                      </p>
                    )}

                    {d.findings.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {d.findings.map((f) => (
                          <li key={f.ref} className="flex flex-wrap items-center gap-2 text-sm">
                            <span className="font-mono text-xs text-indigo-300">{f.ref}</span>
                            <span className={f.merged ? "text-slate-500 line-through" : "text-slate-300"}>
                              {f.title}
                            </span>
                            {f.category && <CategoryBadge category={f.category} />}
                            {f.severity && <span className="text-[11px] text-slate-500">{f.severity}</span>}
                            {f.merged && <span className="text-[11px] text-slate-600">(merged)</span>}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
