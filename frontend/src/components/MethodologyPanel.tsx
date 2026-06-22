import { useState } from "react";
import { api, ApiError, pollJob } from "../lib/api";
import type { Hunt, Job, QueryRow } from "../lib/types";
import { useToast } from "./Toast";
import { Badge, Button, Card, EmptyState, PanelHeader, Spinner } from "./ui";

type SubTab = "description" | "plan" | "queries";

const SUB_TABS: { id: SubTab; label: string }[] = [
  { id: "description", label: "Description" },
  { id: "plan", label: "Plan of Action" },
  { id: "queries", label: "Queries" },
];

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
      <div
        className="h-full rounded-full bg-indigo-500 transition-all duration-500"
        style={{ width: `${Math.max(3, Math.min(100, pct))}%` }}
      />
    </div>
  );
}

function QueryStatusBadge({ row }: { row: QueryRow }) {
  if (row.status === "results")
    return (
      <Badge className="shrink-0 border border-emerald-800 bg-emerald-950 text-emerald-300">
        {row.result_count?.toLocaleString()} events
      </Badge>
    );
  if (row.status === "no_results")
    return (
      <Badge className="shrink-0 border border-slate-700 bg-slate-800 text-slate-400">
        0 events
      </Badge>
    );
  return (
    <Badge className="shrink-0 border border-amber-800 bg-amber-950 text-amber-300">
      {row.outcome ? row.outcome.slice(0, 24) : "pending"}
    </Badge>
  );
}

export default function MethodologyPanel({
  hid,
  tid,
  hunt,
  onRefresh,
}: {
  tid: string;
  hid: string;
  hunt: Hunt | null;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const [job, setJob] = useState<Job | null>(null);
  const [running, setRunning] = useState(false);
  const [sub, setSub] = useState<SubTab>("description");

  const sections = hunt?.methodology_sections ?? null;
  const brief = hunt?.methodology_brief ?? null;
  const hasMethodology = !!hunt?.methodology_text?.trim();
  const analyzed = !!(sections?.available || brief);

  const analyze = async () => {
    setRunning(true);
    setJob({ id: "", status: "queued", progress: 0 });
    try {
      const started = await api.analyzeMethodology(tid, hid);
      const final = await pollJob(tid, hid, started.id, (j) => setJob(j));
      if (final.status === "error") {
        toast.error("Analysis failed — see the log below.");
      } else {
        toast.success("Methodology analyzed.");
      }
      onRefresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Analysis failed.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card>
      <PanelHeader
        title="Hunt Methodology"
        subtitle="Comprehended and structured before any dataset is analyzed"
        right={
          hasMethodology ? (
            <Button variant={analyzed ? "ghost" : "primary"} onClick={analyze} disabled={running}>
              {running ? (
                <>
                  <Spinner /> {job?.progress ?? 0}%
                </>
              ) : analyzed ? (
                "Re-analyze"
              ) : (
                "Analyze"
              )}
            </Button>
          ) : null
        }
      />

      <div className="space-y-4 p-4">
        {/* Hunt params */}
        {hunt && (
          <div className="flex flex-wrap gap-2">
            <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
              Language: {hunt.report_language ?? "English"}
            </Badge>
            {hunt.edr && (
              <Badge className="border border-slate-700 bg-slate-800 text-slate-300">EDR: {hunt.edr}</Badge>
            )}
            {hunt.siem && (
              <Badge className="border border-slate-700 bg-slate-800 text-slate-300">SIEM: {hunt.siem}</Badge>
            )}
            {sections?.available && sections.stats && (
              <Badge className="border border-indigo-800 bg-indigo-950 text-indigo-300">
                {sections.stats.topic_count} topics · {sections.stats.query_count} queries ·{" "}
                {sections.stats.queries_with_results} with results
              </Badge>
            )}
          </div>
        )}

        {/* Live analysis progress + log */}
        {(running || job) && (
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
            <div className="mb-2 flex items-center justify-between gap-3 text-xs">
              <span className="text-slate-300">
                {job?.status === "error"
                  ? "Analysis failed"
                  : job?.current_task ?? "Starting…"}
              </span>
              <span className="font-mono text-slate-500">
                {job?.model ? `model: ${job.model}` : ""} {job?.progress != null ? `· ${job.progress}%` : ""}
              </span>
            </div>
            <ProgressBar pct={job?.progress ?? 0} />
            {!!job?.log?.length && (
              <div className="mt-3 max-h-44 overflow-y-auto rounded bg-black/30 p-2 font-mono text-[11px] leading-relaxed text-slate-400">
                {job.log.map((l, i) => (
                  <div key={i}>
                    <span className="text-slate-600">{l.at.toFixed(1)}s</span> · {l.msg}
                  </div>
                ))}
              </div>
            )}
            {job?.status === "error" && job.error && (
              <p className="mt-2 text-xs text-red-400">{job.error}</p>
            )}
          </div>
        )}

        {/* States */}
        {!hasMethodology ? (
          <EmptyState>
            No methodology provided for this hunt. Add one when creating the hunt (upload or
            paste) so the engine can comprehend the plan of action and queries.
          </EmptyState>
        ) : !analyzed ? (
          <EmptyState>Methodology uploaded but not yet analyzed. Click “Analyze”.</EmptyState>
        ) : (
          <>
            {/* Sub-tabs */}
            <div className="flex gap-1 border-b border-slate-800">
              {SUB_TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setSub(t.id)}
                  className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                    sub === t.id
                      ? "border-indigo-500 text-indigo-300"
                      : "border-transparent text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {t.label}
                  {t.id === "plan" && sections?.plan_of_action?.topics?.length
                    ? ` (${sections.plan_of_action.topics.length})`
                    : ""}
                  {t.id === "queries" && sections?.stats
                    ? ` (${sections.stats.query_count})`
                    : ""}
                </button>
              ))}
            </div>

            {sub === "description" && <DescriptionTab sections={sections} brief={brief} />}
            {sub === "plan" && <PlanTab sections={sections} />}
            {sub === "queries" && <QueriesTab sections={sections} />}
          </>
        )}
      </div>
    </Card>
  );
}

function DescriptionTab({
  sections,
  brief,
}: {
  sections: Hunt["methodology_sections"];
  brief: Hunt["methodology_brief"];
}) {
  return (
    <div className="space-y-5">
      {brief?.hunt_overview && (
        <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/[0.04] p-3">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-indigo-300/80">
            Model’s understanding
          </p>
          <p className="text-sm text-slate-300">{brief.hunt_overview}</p>
          {brief.what_to_expect && (
            <p className="mt-2 text-sm text-slate-400">
              <span className="text-slate-500">What to expect: </span>
              {brief.what_to_expect}
            </p>
          )}
        </div>
      )}

      {sections?.description && (
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Methodology Description
          </p>
          {sections.description.split("\n\n").map((p, i) => (
            <p key={i} className="mb-2 text-sm leading-relaxed text-slate-300">
              {p}
            </p>
          ))}
        </div>
      )}

      {!!sections?.mitre_coverage?.length && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            MITRE ATT&CK Coverage ({sections.mitre_coverage.length})
          </p>
          <div className="overflow-hidden rounded-lg border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/60 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Technique</th>
                  <th className="px-3 py-2 text-left font-medium">Tactic</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {sections.mitre_coverage.map((m, i) => (
                  <tr key={i}>
                    <td className="px-3 py-1.5 font-mono text-xs text-indigo-300">{m.technique}</td>
                    <td className="px-3 py-1.5 text-slate-300">{m.tactic}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function PlanTab({ sections }: { sections: Hunt["methodology_sections"] }) {
  const poa = sections?.plan_of_action;
  if (!poa) return <EmptyState>No plan of action parsed.</EmptyState>;
  return (
    <div className="space-y-4">
      {poa.intro && <p className="text-sm leading-relaxed text-slate-400">{poa.intro}</p>}
      <ol className="space-y-3">
        {poa.topics.map((t, i) => (
          <li key={i} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-slate-500">{i + 1}.</span>
              <span className="text-sm font-medium text-slate-200">{t.name}</span>
              {t.mitre && (
                <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-indigo-300">
                  {t.mitre}
                </span>
              )}
            </div>
            {!!t.indicators?.length && (
              <ul className="mt-2 space-y-1">
                {t.indicators.map((ind, j) => (
                  <li key={j} className="flex gap-2 text-sm text-slate-400">
                    <span className="select-none text-slate-600">›</span>
                    <span>{ind}</span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
      {poa.closing && (
        <p className="border-t border-slate-800 pt-3 text-sm leading-relaxed text-slate-400">
          {poa.closing}
        </p>
      )}
    </div>
  );
}

function QueriesTab({ sections }: { sections: Hunt["methodology_sections"] }) {
  const [open, setOpen] = useState<string | null>(null);
  const topics = sections?.queries ?? [];
  if (!topics.length) return <EmptyState>No queries parsed.</EmptyState>;
  return (
    <div className="space-y-4">
      {topics.map((t) => (
        <div key={t.number} className="rounded-lg border border-slate-800">
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-900/50 px-3 py-2">
            <span className="text-sm font-medium text-slate-200">
              Topic {t.number} — {t.name}
            </span>
            {t.mitre && (
              <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-indigo-300">
                {t.mitre}
              </span>
            )}
          </div>
          <ul className="divide-y divide-slate-800/70">
            {t.rows.map((r, i) => {
              const key = `${t.number}-${i}`;
              const isOpen = open === key;
              return (
                <li key={i} className="px-3 py-2">
                  <div className="flex items-start justify-between gap-3">
                    <button
                      onClick={() => setOpen(isOpen ? null : key)}
                      className="min-w-0 flex-1 text-left text-sm text-slate-300 hover:text-indigo-300"
                    >
                      {r.name}
                    </button>
                    <QueryStatusBadge row={r} />
                  </div>
                  {isOpen && (
                    <pre className="mt-2 max-h-72 overflow-auto rounded bg-black/40 p-2 font-mono text-[11px] leading-relaxed text-slate-400">
                      {r.query}
                    </pre>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
