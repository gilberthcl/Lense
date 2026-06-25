import { useEffect, useState } from "react";
import { api, ApiError, pollJob } from "../lib/api";
import type { Hunt, Job, QACriticalIssue, QAResult } from "../lib/types";
import AnalysisSummaryPanel from "./AnalysisSummaryPanel";
import { useToast } from "./Toast";
import { Button, Card, EmptyState, PanelHeader, Spinner } from "./ui";

const STATUS_STYLE: Record<string, string> = {
  passed: "bg-emerald-900/50 text-emerald-200",
  needs_attention: "bg-amber-900/50 text-amber-200",
  critical: "bg-rose-900/60 text-rose-200",
};
const CHECK_STYLE: Record<string, string> = {
  pass: "text-emerald-300",
  warn: "text-amber-300",
  fail: "text-rose-300",
};
const CHECK_ICON: Record<string, string> = { pass: "✓", warn: "!", fail: "✗" };

export default function QAPanel({
  tid,
  hid,
  reloadKey,
  hunt,
  onRefresh,
}: {
  tid: string;
  hid: string;
  reloadKey: number;
  hunt: Hunt | null;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const [data, setData] = useState<QAResult | null>(null);
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => {
    api
      .getQA(tid, hid)
      .then(setData)
      .catch((e: ApiError) => toast.error(e.message));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid, hid, reloadKey]);

  const runQA = async (fb?: string) => {
    setRunning(true);
    setJob({ id: "", status: "queued", progress: 0, current_task: "Starting QA…" });
    try {
      const started = await api.runQA(tid, hid, fb);
      const done = await pollJob(tid, hid, String(started.id), setJob);
      if (done.status === "error") toast.error(done.error ?? "QA failed");
      else {
        const r = done.result as { status?: string; critical?: number } | undefined;
        toast.success(`QA ${r?.status ?? "done"} — ${r?.critical ?? 0} critical issue(s)`);
        setFeedback("");
        load();
      }
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setRunning(false);
    }
  };

  const toggleAuto = async () => {
    if (!hunt) return;
    try {
      await api.setAutoQa(tid, hid, !hunt.auto_qa);
      onRefresh();
    } catch (e) {
      toast.error((e as ApiError).message);
    }
  };

  // Act on a critical issue's recommended fix, using the existing phase
  // endpoints. Re-analysis is sequenced (one dataset at a time) — firing them
  // concurrently overwhelms a local Ollama on limited RAM and they error out.
  const remediate = async (issue: QACriticalIssue) => {
    const fix = issue.fix ?? "";
    try {
      if (fix === "reanalyze_datasets") {
        const ids = (issue.meta?.dataset_ids ?? []).filter(
          (x): x is number => typeof x === "number",
        );
        if (!ids.length) {
          toast.error("No dataset references recorded — re-analyze from the Datasets tab.");
          return;
        }
        setBusy(fix);
        setRunning(true);
        let ok = 0;
        let failed = 0;
        for (let k = 0; k < ids.length; k++) {
          setJob({ id: "", status: "running", progress: 0,
            current_task: `Re-analyzing dataset ${k + 1}/${ids.length}…` });
          try {
            const started = await api.analyzeDataset(tid, hid, String(ids[k]));
            const done = await pollJob(tid, hid, String(started.id), setJob);
            done.status === "error" ? (failed += 1) : (ok += 1);
          } catch {
            failed += 1;
          }
        }
        if (ok) {
          // Findings changed → correlation and QA are now stale. Re-run both,
          // in order, so the operator ends on a fresh QA verdict.
          setJob({ id: "", status: "running", progress: 0, current_task: "Re-running correlation…" });
          const corr = await api.runCorrelation(tid, hid);
          await pollJob(tid, hid, String(corr.id), setJob);
          toast.success(`Re-analyzed ${ok} dataset(s)${failed ? `, ${failed} failed` : ""}. Re-running QA…`);
          onRefresh();
          await runQA(); // re-runs QA, polls, reloads
        } else {
          toast.error(`All ${failed} re-analysis attempt(s) failed — check 'lense logs backend' for the cause.`);
          onRefresh();
        }
      } else if (fix === "run_correlation") {
        setBusy(fix);
        const started = await api.runCorrelation(tid, hid);
        await pollJob(tid, hid, String(started.id), () => {});
        toast.success("Correlation finished. Re-run QA to re-check.");
        onRefresh();
      } else {
        toast.error("This issue has no automatic fix — resolve it on the relevant tab.");
      }
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setRunning(false);
      setBusy(null);
    }
  };

  const rollback = async () => {
    setBusy("rollback");
    try {
      const r = await api.rollbackQA(tid, hid);
      toast.success(
        r.reverted_findings
          ? `Reverted ${r.reverted_fields} field(s) across ${r.reverted_findings} finding(s).`
          : "Nothing to roll back.",
      );
      load();
      onRefresh();
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  const FIX_LABEL: Record<string, string> = {
    reanalyze_datasets: "Re-analyze affected datasets",
    run_correlation: "Run correlation",
  };

  const report = data?.report ?? null;
  const flagged = (data?.findings ?? []).filter(
    (f) => f.qa && f.qa.status && f.qa.status !== "pass",
  );
  const reversible = (report?.actions ?? []).filter(
    (a) => a.action === "gap_filled" && !a.rolled_back,
  );

  return (
    <div className="space-y-4">
      <Card>
        <PanelHeader
          title="QA phase"
          subtitle="Verifies analysis & correlation ran correctly and every finding is complete and grounded"
          right={
            <div className="flex items-center gap-3">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={!!hunt?.auto_qa}
                  onChange={toggleAuto}
                  disabled={!hunt}
                  className="h-3.5 w-3.5 accent-indigo-500"
                />
                Auto-run after correlation
              </label>
              <Button onClick={() => runQA()} disabled={running}>
                {running ? <Spinner /> : "Run QA"}
              </Button>
            </div>
          }
        />
        <div className="space-y-4 p-4">
          {(running || job) && (
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="text-slate-300">
                  {job?.status === "error" ? "QA failed" : job?.current_task ?? "Starting…"}
                </span>
                <span className="font-mono text-slate-500">
                  {job?.progress != null ? `${Math.round(job.progress)}%` : ""}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded bg-slate-800">
                <div className="h-full bg-indigo-500 transition-all" style={{ width: `${Math.max(3, job?.progress ?? 0)}%` }} />
              </div>
              {!!job?.log?.length && (
                <div className="mt-2 max-h-32 overflow-y-auto rounded bg-black/30 p-2 font-mono text-[11px] text-slate-400">
                  {job.log.map((l, i) => (
                    <div key={i}>
                      <span className="text-slate-600">{l.at.toFixed(1)}s</span> · {l.msg}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {data === null ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner /> Loading…
            </div>
          ) : !report ? (
            <EmptyState>
              QA hasn’t run yet. It verifies the analysis and correlation phases and
              checks every finding for completeness and evidence-grounding. The report
              can only be generated once QA passes.
            </EmptyState>
          ) : (
            <>
              {/* Overall status */}
              <div className="flex flex-wrap items-center gap-3">
                <span className={`rounded px-2 py-1 text-sm font-semibold uppercase tracking-wide ${STATUS_STYLE[report.status] ?? "bg-slate-800"}`}>
                  {report.status.replace("_", " ")}
                </span>
                <span className="text-sm text-slate-400">
                  {report.totals.findings} finding(s) · avg completeness {report.totals.avg_completeness}% ·{" "}
                  {report.totals.complete} complete · {report.totals.incomplete} incomplete ·{" "}
                  {report.totals.minor ?? 0} minor · {report.totals.critical} critical ·{" "}
                  {report.totals.gap_filled} auto-filled
                </span>
              </div>

              {/* Stage checklist */}
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Pipeline checks</p>
                <ul className="space-y-1">
                  {report.stage_checks.map((c) => (
                    <li key={c.stage} className="flex items-start gap-2 text-sm">
                      <span className={`font-mono ${CHECK_STYLE[c.status] ?? "text-slate-400"}`}>{CHECK_ICON[c.status] ?? "·"}</span>
                      <span className="text-slate-300">
                        <b>{c.stage}:</b> {c.detail}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* What QA actually did this run — always shown, so the phase is
                  never a black box even when it changed nothing. */}
              <div className="rounded border border-slate-800 bg-slate-950/40 p-3">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  What QA did this run
                </p>
                <ul className="space-y-1 text-sm text-slate-300">
                  {(report.totals.activity ?? []).map((line, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-slate-600">·</span>
                      <span>{line}</span>
                    </li>
                  ))}
                  {!(report.totals.activity ?? []).length && (
                    <li className="text-slate-500">
                      {report.totals.judged ?? 0} finding(s) judged · {report.totals.gap_filled} auto-filled
                    </li>
                  )}
                </ul>
                {/* Per-finding edits, with rollback */}
                {report.actions.some((a) => a.action === "gap_filled") && (
                  <div className="mt-2.5 border-t border-slate-800 pt-2.5">
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                        Findings edited by QA
                      </span>
                      {reversible.length > 0 && (
                        <Button variant="ghost" onClick={rollback} disabled={busy !== null}>
                          {busy === "rollback" ? <Spinner /> : `Roll back ${reversible.length} edit(s)`}
                        </Button>
                      )}
                    </div>
                    <ul className="space-y-1 text-sm text-slate-400">
                      {report.actions
                        .filter((a) => a.action === "gap_filled")
                        .map((a, i) => (
                          <li key={i} className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs text-indigo-300">{a.finding_ref}</span>
                            <span>filled {(a.fields ?? []).join(", ")}</span>
                            {a.rolled_back && (
                              <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
                                rolled back
                              </span>
                            )}
                          </li>
                        ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Critical issues awaiting decision */}
              {report.critical_issues.length > 0 && (
                <div className="rounded border border-rose-900/50 bg-rose-950/20 p-3">
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-rose-300">
                    Critical issues — your decision needed ({report.critical_issues.length})
                  </p>
                  <ul className="space-y-2 text-sm text-slate-300">
                    {report.critical_issues.map((ci, i) => (
                      <li key={i} className="flex flex-wrap items-center gap-2">
                        {ci.finding_ref && <span className="font-mono text-xs text-rose-300">{ci.finding_ref}</span>}
                        {ci.stage && <span className="font-mono text-xs text-rose-300">{ci.stage}</span>}
                        <span className="flex-1 min-w-[12rem]">{ci.detail}</span>
                        {ci.fix && FIX_LABEL[ci.fix] && (
                          <Button
                            variant="ghost"
                            onClick={() => remediate(ci)}
                            disabled={busy !== null || running}
                          >
                            {busy === ci.fix ? <Spinner /> : FIX_LABEL[ci.fix]}
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-[11px] text-slate-500">
                    Re-analyzing runs the datasets one at a time (a local model can't analyze
                    them in parallel), then automatically re-runs correlation and QA — since
                    each phase feeds the next. Or resolve on the relevant tab (e.g. reject the
                    finding on Findings) and re-run QA. The report stays blocked until QA passes.
                  </p>
                </div>
              )}

              {/* Phase-level auto-actions (e.g. correlation run by QA) */}
              {report.actions.some((a) => a.action !== "gap_filled") && (
                <div>
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Phase actions</p>
                  <ul className="space-y-1 text-sm text-slate-400">
                    {report.actions
                      .filter((a) => a.action !== "gap_filled")
                      .map((a, i) => (
                        <li key={i}>{a.detail ?? a.action}</li>
                      ))}
                  </ul>
                </div>
              )}

              {/* Per-finding QA */}
              {flagged.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Findings needing attention ({flagged.length})
                  </p>
                  <div className="space-y-1.5">
                    {flagged.map((f) => (
                      <div key={f.ref} className="rounded border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs text-indigo-300">{f.ref}</span>
                          <span className="text-slate-300">{f.title}</span>
                          <span className="text-[11px] text-slate-500">{f.qa?.status} · {f.qa?.score}%</span>
                        </div>
                        {!!f.qa?.gaps?.length && (
                          <p className="mt-1 text-[11px] text-amber-300">Missing: {f.qa.gaps.join(", ")}</p>
                        )}
                        {!!f.qa?.grounding_issues?.length && (
                          <p className="mt-1 text-[11px] text-rose-300">{f.qa.grounding_issues.join("; ")}</p>
                        )}
                        {f.qa?.judge?.suggested_fix && (
                          <p className="mt-1 text-[11px] text-slate-400">Reviewer: {f.qa.judge.suggested_fix}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Re-run with feedback */}
              <div className="rounded border border-slate-800 bg-slate-950/40 p-3">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Re-run QA with feedback</p>
                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  placeholder="Optional guidance for the QA reviewer (e.g. 'be stricter on severity calibration')…"
                  className="w-full rounded border border-slate-700 bg-slate-950 p-2 text-sm text-slate-200"
                  rows={2}
                />
                <div className="mt-2">
                  <Button variant="ghost" onClick={() => runQA(feedback || undefined)} disabled={running}>
                    {running ? <Spinner /> : "Re-run QA"}
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </Card>

      {/* Analysis summary (moved into the QA tab) */}
      <AnalysisSummaryPanel tid={tid} hid={hid} reloadKey={reloadKey} />
    </div>
  );
}
