import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { LearningEventItem, LearningLog } from "../../lib/types";
import { useToast } from "../Toast";
import { Badge, Card, EmptyState, PanelHeader, Spinner, fmtDate } from "../ui";

// How each learning source is phrased for a non-technical reader.
const SOURCE_LABEL: Record<string, string> = {
  live_feedback: "Analyst feedback on a finding",
  missed_finding: "Missed finding added offline",
  training_hunt: "Training hunt ingestion",
  import: "Imported finding",
};

const DISPOSITION_CLS: Record<string, string> = {
  accepted: "bg-emerald-950 text-emerald-300 border border-emerald-800",
  added: "bg-emerald-950 text-emerald-300 border border-emerald-800",
  partial: "bg-amber-950 text-amber-300 border border-amber-800",
  rejected: "bg-red-950 text-red-300 border border-red-800",
};

function EventRow({ ev }: { ev: LearningEventItem }) {
  return (
    <li className="rounded border border-slate-800 bg-slate-950/40 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-slate-500">{fmtDate(ev.created_at)}</span>
        <Badge className="border border-slate-700 bg-slate-800 text-slate-300">{ev.stage}</Badge>
        {ev.disposition && (
          <Badge className={DISPOSITION_CLS[ev.disposition] ?? "border border-slate-700 bg-slate-800 text-slate-300"}>
            {ev.disposition}
          </Badge>
        )}
        {ev.score != null && (
          <span className="text-[11px] text-slate-400">rated {ev.score}/10</span>
        )}
        <span className="text-[11px] text-slate-500">
          {SOURCE_LABEL[ev.source] ?? ev.source}
        </span>
        {ev.hunt_name && (
          <span className="ml-auto text-[11px] text-indigo-300">{ev.hunt_name}</span>
        )}
      </div>
      {ev.lesson && (
        <p className="mt-1.5 text-xs text-slate-200">
          <span className="text-slate-500">Lesson learned: </span>
          {ev.lesson}
        </p>
      )}
      {ev.feedback && (
        <p className="mt-1 text-[11px] text-slate-400">
          <span className="text-slate-600">Your feedback: </span>
          {ev.feedback}
        </p>
      )}
      {!ev.lesson && !ev.feedback && (
        <p className="mt-1 text-[11px] italic text-slate-600">
          Recorded as a {ev.disposition ?? "learning"} signal (no written note).
        </p>
      )}
    </li>
  );
}

/**
 * Per-client learning log — the audit trail behind "learning without retraining".
 * Every accept / reject / partial / added finding that taught this client's model
 * is listed, newest first, with a timestamp and the distilled lesson. Read-only.
 */
export default function ClientLearningLog({ tid }: { tid: string }) {
  const toast = useToast();
  const [data, setData] = useState<LearningLog | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api
      .getLearningLog(tid)
      .then(setData)
      .catch((e: ApiError) => toast.error(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  const stages = data ? Object.entries(data.summary.by_stage) : [];

  return (
    <Card>
      <PanelHeader
        title="Learning log"
        subtitle="Every action that taught this client's model — newest first, with timestamps. This is the proof of what was learned."
        right={
          <button
            onClick={load}
            className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            Refresh
          </button>
        }
      />
      <div className="p-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : !data || data.count === 0 ? (
          <EmptyState>
            Nothing learned yet. Accept, reject, or refine a finding with feedback — or add a
            missed finding — and it will be logged here with a timestamp.
          </EmptyState>
        ) : (
          <>
            {/* Per-stage roll-up so you can see WHERE the learning happened. */}
            {stages.length > 0 && (
              <div className="mb-4 flex flex-wrap gap-2">
                {stages.map(([stage, s]) => (
                  <div
                    key={stage}
                    className="rounded border border-slate-800 bg-slate-950/40 px-3 py-1.5 text-xs"
                  >
                    <span className="font-medium text-slate-300">{stage}</span>
                    <span className="ml-2 text-slate-500">
                      {s.count} event{s.count === 1 ? "" : "s"}
                      {s.avg_score != null ? ` · avg ${s.avg_score}/10` : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <p className="mb-2 text-xs text-slate-500">
              {data.count} learning event{data.count === 1 ? "" : "s"} total.
            </p>
            <ul className="space-y-2">
              {data.events.map((ev) => (
                <EventRow key={ev.id} ev={ev} />
              ))}
            </ul>
          </>
        )}
      </div>
    </Card>
  );
}
