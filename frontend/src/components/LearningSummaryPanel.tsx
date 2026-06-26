import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { LearningSummary } from "../lib/types";
import { Badge, Card, PanelHeader, Spinner } from "./ui";

/**
 * Learning summary (W4) — the per-stage record of what the operator taught the
 * model on this hunt. Rendered at the bottom of the review surface.
 */
export default function LearningSummaryPanel({
  tid,
  hid,
  reloadKey = 0,
}: {
  tid: string;
  hid: string;
  reloadKey?: number;
}) {
  const [data, setData] = useState<LearningSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getLearningSummary(tid, hid)
      .then(setData)
      .catch((e: ApiError) => setError(e.message));
  }, [tid, hid, reloadKey]);

  if (error) return null;
  if (!data) {
    return (
      <Card className="mt-4">
        <div className="flex items-center gap-2 p-4 text-sm text-slate-500">
          <Spinner /> Loading learning summary…
        </div>
      </Card>
    );
  }

  const stages = Object.entries(data.by_stage);

  return (
    <Card className="mt-4">
      <PanelHeader
        title="Learning summary"
        subtitle="What you taught the model on this hunt — fed to RAG now, and to training later"
        right={
          <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
            {data.total} signal(s)
          </Badge>
        }
      />
      <div className="p-4">
        {stages.length === 0 ? (
          <p className="text-sm text-slate-500">
            No learning signals yet. Disposition findings or rate any stage to start teaching the model.
          </p>
        ) : (
          <div className="space-y-3">
            {stages.map(([stage, s]) => (
              <div key={stage} className="rounded border border-slate-800 bg-slate-950/40 p-3">
                <div className="mb-1.5 flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold capitalize text-slate-200">{stage}</span>
                  <span className="text-[11px] text-slate-500">{s.count} signal(s)</span>
                  {s.avg_score != null && (
                    <Badge className="border border-indigo-800 bg-indigo-950 text-indigo-300">
                      avg {s.avg_score}/10
                    </Badge>
                  )}
                  {Object.entries(s.dispositions).map(([d, n]) => (
                    <span key={d} className="text-[11px] text-slate-400">{d}: {n}</span>
                  ))}
                </div>
                {s.recent.length > 0 && (
                  <ul className="space-y-1 text-[11px] text-slate-400">
                    {s.recent.map((r, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-slate-600">·</span>
                        <span>{r.feedback || r.summary}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
