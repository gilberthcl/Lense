import { useEffect, useRef, useState } from "react";
import { api, ApiError, pollJob } from "../lib/api";
import type { Hunt, Job, MethodologyBrief, QueryRow } from "../lib/types";
import { useToast } from "./Toast";
import { IconChevron } from "./icons";
import StageFeedback from "./StageFeedback";
import { Badge, Button, Card, EmptyState, PanelHeader, Spinner, Textarea } from "./ui";

type SubTab = "description" | "plan" | "queries" | "ai";

const SUB_TABS: { id: SubTab; label: string }[] = [
  { id: "description", label: "Description" },
  { id: "plan", label: "Plan of Action" },
  { id: "queries", label: "Queries" },
  { id: "ai", label: "AI Analysis" },
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
  const [uploading, setUploading] = useState(false);
  const [sub, setSub] = useState<SubTab>("description");
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedback, setFeedback] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const sections = hunt?.methodology_sections ?? null;
  const brief = hunt?.methodology_brief ?? null;
  const hasMethodology = !!hunt?.methodology_text?.trim();
  const docChars = hunt?.methodology_text?.length ?? 0;
  const analyzed = !!(sections?.available || brief);

  const uploadDoc = async (file?: File) => {
    if (!file) return;
    setUploading(true);
    try {
      await api.uploadMethodology(tid, hid, file);
      toast.success(`Loaded ${file.name}. Click “Analyze” to comprehend it.`);
      if (fileRef.current) fileRef.current.value = "";
      onRefresh();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const watch = async (jobId: string) => {
    setRunning(true);
    try {
      const final = await pollJob(tid, hid, jobId, (j) => setJob(j));
      if (final.status === "error") toast.error("Analysis failed — see the log below.");
      else if (final.status === "cancelled") toast.info("Analysis cancelled.");
      else {
        toast.success("Methodology analyzed.");
        onRefresh();
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Analysis failed.");
    } finally {
      setRunning(false);
    }
  };

  const analyze = async (feedback?: string) => {
    setJob({ id: "", status: "queued", progress: 0 });
    try {
      const started = await api.analyzeMethodology(tid, hid, feedback);
      await watch(started.id);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Analysis failed.");
      setRunning(false);
    }
  };

  const cancel = async () => {
    if (!job?.id) return;
    try {
      await api.cancelHuntJob(tid, hid, job.id);
    } catch {
      /* polling will reflect the final state */
    }
  };

  // Re-attach to an in-progress methodology analysis after a tab switch / reload.
  useEffect(() => {
    let dead = false;
    api
      .listHuntJobs(tid, hid)
      .then((js) => {
        const a = js.find(
          (j) => j.phase === "methodology" && (j.status === "running" || j.status === "queued"),
        );
        if (a && !dead) {
          setJob(a);
          watch(a.id);
        }
      })
      .catch(() => undefined);
    return () => {
      dead = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid, hid]);

  return (
    <Card>
      <PanelHeader
        title="Hunt Methodology"
        subtitle="Comprehended and structured before any dataset is analyzed"
        right={
          <div className="flex items-center gap-2">
            <StageFeedback tid={tid} hid={hid} stage="methodology" label="Methodology" />
            <input
              ref={fileRef}
              type="file"
              accept=".docx,.txt,.md,.markdown"
              className="hidden"
              onChange={(e) => uploadDoc(e.target.files?.[0])}
            />
            <Button variant="ghost" onClick={() => fileRef.current?.click()} disabled={uploading || running}>
              {uploading ? <Spinner /> : hasMethodology ? "Replace doc" : "Upload doc"}
            </Button>
            {hasMethodology && (
              <Button variant={analyzed ? "ghost" : "primary"} onClick={() => analyze()} disabled={running}>
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
            )}
            {hasMethodology && analyzed && (
              <Button
                variant={showFeedback ? "primary" : "ghost"}
                onClick={() => setShowFeedback((s) => !s)}
                disabled={running}
              >
                Re-analyze with feedback
              </Button>
            )}
          </div>
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
            <Badge
              className={
                hasMethodology
                  ? "border border-emerald-800 bg-emerald-950 text-emerald-300"
                  : "border border-slate-700 bg-slate-800 text-slate-400"
              }
            >
              {hasMethodology ? `Doc loaded · ${docChars.toLocaleString()} chars` : "No doc"}
            </Badge>
            <Badge
              className={
                brief
                  ? "border border-emerald-800 bg-emerald-950 text-emerald-300"
                  : "border border-amber-800 bg-amber-950 text-amber-300"
              }
            >
              {brief ? "AI analyzed ✓" : "Not AI-analyzed"}
            </Badge>
          </div>
        )}

        {/* Re-analyze with feedback — corrects the model's prior understanding */}
        {showFeedback && analyzed && !running && (
          <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/[0.05] p-3">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-indigo-300">
              What did the model get wrong?
            </p>
            <Textarea
              rows={3}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="e.g. You misread topic 3 — the persistence check is about scheduled tasks, not services. Treat the 'no results' queries as cleared, not skipped."
            />
            <div className="mt-2 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => { setShowFeedback(false); setFeedback(""); }}>
                Cancel
              </Button>
              <Button
                variant="primary"
                disabled={!feedback.trim()}
                onClick={() => { analyze(feedback.trim()); setShowFeedback(false); setFeedback(""); }}
              >
                Re-analyze with this feedback
              </Button>
            </div>
          </div>
        )}

        {/* Live analysis progress + log */}
        {(running || job) && (
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
            <div className="mb-2 flex items-center justify-between gap-3 text-xs">
              <span className="text-slate-300">
                {job?.status === "error"
                  ? "Analysis failed"
                  : job?.status === "cancelled"
                    ? "Cancelled"
                    : job?.current_task ?? "Starting…"}
              </span>
              <div className="flex items-center gap-3">
                <span className="font-mono text-slate-500">
                  {job?.model ? `model: ${job.model}` : ""} {job?.progress != null ? `· ${job.progress}%` : ""}
                </span>
                {running && (job?.status === "running" || job?.status === "queued") && (
                  <button onClick={cancel} className="text-red-400 hover:text-red-300">
                    Cancel
                  </button>
                )}
              </div>
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
            {sub === "ai" && <AiAnalysisTab brief={brief} onAnalyze={analyze} running={running} />}
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

function AiBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      {children}
    </div>
  );
}

function AiAnalysisTab({
  brief,
  onAnalyze,
  running,
}: {
  brief: MethodologyBrief | null | undefined;
  onAnalyze: () => void;
  running: boolean;
}) {
  if (!brief) {
    return (
      <div className="space-y-3">
        <EmptyState>
          The methodology hasn’t been analyzed by the AI yet. The model reads the full
          methodology and explains what the hunt is about, what was covered, and which
          queries returned results.
        </EmptyState>
        <Button variant="primary" onClick={onAnalyze} disabled={running}>
          {running ? <Spinner /> : "Run AI analysis"}
        </Button>
      </div>
    );
  }

  const topics = brief.topics ?? [];
  const queries = brief.executed_queries ?? [];
  const fps = brief.known_false_positives ?? [];

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/[0.04] p-3">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-indigo-300/80">
          What the model understood this hunt is about
        </p>
        {brief.hunt_overview ? (
          <p className="text-sm leading-relaxed text-slate-300">{brief.hunt_overview}</p>
        ) : (
          <p className="text-sm italic text-slate-500">No overview returned.</p>
        )}
      </div>

      {brief.scope && (
        <AiBlock title="Scope">
          <p className="text-sm text-slate-300">{brief.scope}</p>
        </AiBlock>
      )}
      {brief.what_to_expect && (
        <AiBlock title="What to expect in the datasets">
          <p className="text-sm text-slate-300">{brief.what_to_expect}</p>
        </AiBlock>
      )}

      {!!topics.length && (
        <AiBlock title={`Topics the model identified (${topics.length})`}>
          <ul className="space-y-2">
            {topics.map((t, i) => (
              <li key={i} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-200">
                    {t.number ? `${t.number}. ` : ""}
                    {t.name}
                  </span>
                  {(t.mitre ?? []).map((m, j) => (
                    <span key={j} className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-indigo-300">
                      {m}
                    </span>
                  ))}
                </div>
                {t.objective && <p className="mt-1 text-xs text-slate-400">{t.objective}</p>}
                {t.malicious_indicators && (
                  <p className="mt-1 text-xs text-slate-400">
                    <span className="text-red-400/80">Malicious: </span>
                    {t.malicious_indicators}
                  </p>
                )}
                {t.expected_benign && (
                  <p className="mt-1 text-xs text-slate-400">
                    <span className="text-emerald-400/80">Expected benign: </span>
                    {t.expected_benign}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </AiBlock>
      )}

      {!!queries.length && (
        <AiBlock title="Executed queries the model noted">
          <ul className="space-y-1">
            {queries.map((q, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                <Badge
                  className={
                    q.had_results
                      ? "shrink-0 border border-emerald-800 bg-emerald-950 text-emerald-300"
                      : "shrink-0 border border-slate-700 bg-slate-800 text-slate-400"
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
        </AiBlock>
      )}

      {!!fps.length && (
        <AiBlock title="Known false positives the model flagged">
          <ul className="list-inside list-disc text-sm text-slate-300">
            {fps.map((fp, i) => (
              <li key={i}>{fp}</li>
            ))}
          </ul>
        </AiBlock>
      )}

      {brief.note && <p className="text-xs italic text-amber-400/80">{brief.note}</p>}
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
                      className="flex min-w-0 flex-1 items-start gap-2 text-left text-sm text-slate-300 hover:text-indigo-300"
                    >
                      <IconChevron
                        width={14}
                        height={14}
                        className={`mt-0.5 shrink-0 text-slate-500 transition-transform ${isOpen ? "rotate-90" : ""}`}
                      />
                      <span className="min-w-0">{r.name}</span>
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
