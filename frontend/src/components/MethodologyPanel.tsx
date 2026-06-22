import { useState } from "react";
import { api, ApiError, pollJob } from "../lib/api";
import type { Hunt } from "../lib/types";
import { useToast } from "./Toast";
import { Badge, Button, Card, EmptyState, PanelHeader, Spinner } from "./ui";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </p>
      {children}
    </div>
  );
}

export default function MethodologyPanel({
  tid,
  hid,
  hunt,
  onRefresh,
}: {
  tid: string;
  hid: string;
  hunt: Hunt | null;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);

  const brief = hunt?.methodology_brief ?? null;
  const hasMethodology = !!hunt?.methodology_text?.trim();

  const reanalyze = async () => {
    setRunning(true);
    setProgress(0);
    try {
      const job = await api.analyzeMethodology(tid, hid);
      await pollJob(tid, hid, job.id, (j) => setProgress(j.progress ?? 0));
      toast.success("Methodology comprehended.");
      onRefresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Comprehension failed.");
    } finally {
      setRunning(false);
      setProgress(null);
    }
  };

  return (
    <Card>
      <PanelHeader
        title="Hunt Methodology"
        subtitle="Comprehended before any dataset is analyzed"
        right={
          hasMethodology ? (
            <Button variant="ghost" onClick={reanalyze} disabled={running}>
              {running ? (
                <>
                  <Spinner /> {progress ?? 0}%
                </>
              ) : brief ? (
                "Re-comprehend"
              ) : (
                "Comprehend now"
              )}
            </Button>
          ) : null
        }
      />
      <div className="space-y-4 p-4">
        {hunt && (
          <div className="flex flex-wrap gap-2">
            <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
              Language: {hunt.report_language ?? "English"}
            </Badge>
            {hunt.edr && (
              <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
                EDR: {hunt.edr}
              </Badge>
            )}
            {hunt.siem && (
              <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
                SIEM: {hunt.siem}
              </Badge>
            )}
          </div>
        )}

        {!hasMethodology ? (
          <EmptyState>
            No methodology provided for this hunt. Add one when creating the hunt
            (upload or paste) so the engine can comprehend the plan of action.
          </EmptyState>
        ) : !brief ? (
          <EmptyState>
            Methodology uploaded but not yet comprehended. Click “Comprehend now”.
          </EmptyState>
        ) : (
          <>
            {brief.hunt_overview && (
              <Section title="Overview">
                <p className="text-sm text-slate-300">{brief.hunt_overview}</p>
              </Section>
            )}
            {brief.scope && (
              <Section title="Scope">
                <p className="text-sm text-slate-300">{brief.scope}</p>
              </Section>
            )}
            {brief.what_to_expect && (
              <Section title="What to expect in the datasets">
                <p className="text-sm text-slate-300">{brief.what_to_expect}</p>
              </Section>
            )}
            {!!brief.topics?.length && (
              <Section title={`Topics (${brief.topics.length})`}>
                <ul className="space-y-2">
                  {brief.topics.map((t, i) => (
                    <li
                      key={i}
                      className="rounded border border-slate-800 bg-slate-950/40 p-2.5"
                    >
                      <p className="text-sm font-medium text-slate-200">
                        {t.number ? `${t.number}. ` : ""}
                        {t.name}
                      </p>
                      {t.objective && (
                        <p className="mt-0.5 text-xs text-slate-400">{t.objective}</p>
                      )}
                      {!!t.mitre?.length && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {t.mitre.map((m, j) => (
                            <span
                              key={j}
                              className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-indigo-300"
                            >
                              {m}
                            </span>
                          ))}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {!!brief.executed_queries?.length && (
              <Section title="Executed queries">
                <ul className="space-y-1 text-sm text-slate-300">
                  {brief.executed_queries.map((q, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <Badge
                        className={
                          q.had_results
                            ? "border border-emerald-800 bg-emerald-950 text-emerald-300"
                            : "border border-slate-700 bg-slate-800 text-slate-400"
                        }
                      >
                        {q.had_results ? "results" : "no results"}
                      </Badge>
                      <span>
                        {q.topic ? `[${q.topic}] ` : ""}
                        {q.summary}
                      </span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {!!brief.known_false_positives?.length && (
              <Section title="Known false positives">
                <ul className="list-inside list-disc text-sm text-slate-300">
                  {brief.known_false_positives.map((fp, i) => (
                    <li key={i}>{fp}</li>
                  ))}
                </ul>
              </Section>
            )}
            {brief.note && (
              <p className="text-xs italic text-amber-400/80">{brief.note}</p>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
