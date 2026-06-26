import { Fragment, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type {
  DispositionReflection,
  Finding,
  FindingRevisionResult,
  FindingStatus,
} from "../lib/types";
import { useToast } from "./Toast";
import MissedFindingWizard from "./MissedFindingWizard";
import {
  Button,
  Card,
  CategoryBadge,
  EmptyState,
  FindingStatusBadge,
  PanelHeader,
  Spinner,
  Textarea,
} from "./ui";

type PatchBody = { status?: FindingStatus; reviewer_notes?: string };

function prettyJson(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") {
    // Try to parse JSON-in-a-string for nicer display.
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

// Render a single list item that may be a scalar OR an object (e.g. MITRE comes
// back as [{technique_id, name}]). Objects are flattened to a readable label
// instead of the default "[object Object]".
function stringifyItem(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    const id = o.technique_id ?? o.technique ?? o.id ?? o.tactic_id;
    const name = o.name ?? o.title ?? o.technique_name ?? o.tactic ?? o.value;
    const label = [id, name].filter((x) => x != null && x !== "").join(" — ");
    if (label) return label;
    // Fallback: join the scalar values so we never show "[object Object]".
    const scalars = Object.values(o).filter(
      (x) => typeof x === "string" || typeof x === "number",
    );
    return scalars.length ? scalars.map(String).join(" · ") : JSON.stringify(v);
  }
  return String(v);
}

function asList(value: unknown): string[] {
  if (value == null) return [];
  if (Array.isArray(value)) return value.map(stringifyItem).filter(Boolean);
  if (typeof value === "string") {
    const trimmed = value.trim();
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed.map(stringifyItem).filter(Boolean);
    } catch {
      // fall through
    }
    return trimmed ? [trimmed] : [];
  }
  if (typeof value === "object") return [stringifyItem(value)];
  return [String(value)];
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      {children}
    </div>
  );
}

function Pills({ items }: { items: string[] }) {
  if (items.length === 0) return <p className="text-sm text-slate-600">—</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((it, i) => (
        <span
          key={i}
          className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-300"
        >
          {it}
        </span>
      ))}
    </div>
  );
}

function FindingDetail({
  finding,
  onPatch,
  onDispose,
  onRegenerate,
  onDelete,
  patching,
}: {
  finding: Finding;
  onPatch: (body: PatchBody) => void;
  onDispose: (
    action: "accept" | "reject" | "partial",
    feedback?: string,
    score?: number,
  ) => Promise<DispositionReflection | null>;
  onRegenerate: (feedback: string) => Promise<FindingRevisionResult | null>;
  onDelete: () => void;
  patching: boolean;
}) {
  const [notes, setNotes] = useState(finding.reviewer_notes ?? "");
  const notesDirty = notes !== (finding.reviewer_notes ?? "");
  const [mode, setMode] = useState<"accept" | "partial" | "reject" | null>(null);
  const [feedback, setFeedback] = useState("");
  const [score, setScore] = useState<number | null>(null);
  const [revision, setRevision] = useState<FindingRevisionResult | null>(null);
  const [reflection, setReflection] = useState<DispositionReflection | null>(null);
  return (
    <div className="space-y-4 border-t border-slate-800 bg-slate-950/60 p-4">
      {finding.summary && (
        <Field label="Summary">
          <p className="whitespace-pre-wrap text-sm text-slate-300">
            {finding.summary}
          </p>
        </Field>
      )}

      {/* Analysis context — the structured detail behind the finding, for
          report-writing. */}
      {(finding.source_dataset ||
        finding.time_range ||
        (finding.entities && Object.keys(finding.entities).length > 0) ||
        finding.behavioral_context ||
        (finding.evidence_rows && finding.evidence_rows.length > 0)) && (
        <Field label="Analysis context">
          <div className="space-y-2 rounded border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
            {finding.source_dataset && (
              <div>
                <span className="text-xs uppercase tracking-wide text-slate-500">Source dataset: </span>
                <span className="break-all">{finding.source_dataset}</span>
              </div>
            )}
            {finding.time_range && (
              <div className="text-xs text-slate-400">
                <span className="uppercase tracking-wide text-slate-500">Time range: </span>
                {(finding.time_range as Record<string, unknown>).start
                  ? `${(finding.time_range as Record<string, unknown>).start} → ${(finding.time_range as Record<string, unknown>).end}`
                  : prettyJson(finding.time_range)}
              </div>
            )}
            {finding.entities &&
              Object.entries(finding.entities).map(([type, vals]) =>
                vals && vals.length ? (
                  <div key={type}>
                    <span className="text-xs uppercase tracking-wide text-slate-500">{type}: </span>
                    <Pills items={vals} />
                  </div>
                ) : null,
              )}
            {finding.behavioral_context && (
              <details>
                <summary className="cursor-pointer text-xs uppercase tracking-wide text-slate-500">
                  Behavioral signals
                </summary>
                <pre className="mt-1 max-h-48 overflow-auto rounded bg-slate-950 p-2 font-mono text-[11px] text-slate-300">
                  {prettyJson(finding.behavioral_context)}
                </pre>
              </details>
            )}
            {finding.evidence_rows && finding.evidence_rows.length > 0 && (
              <details>
                <summary className="cursor-pointer text-xs uppercase tracking-wide text-slate-500">
                  Evidence rows ({finding.evidence_rows.length})
                </summary>
                <pre className="mt-1 max-h-60 overflow-auto rounded bg-slate-950 p-2 font-mono text-[11px] text-slate-300">
                  {prettyJson(finding.evidence_rows)}
                </pre>
              </details>
            )}
          </div>
        </Field>
      )}

      {finding.enrichment?.note && (
        <Field label="Correlation enrichment">
          <div className="rounded border border-emerald-900/40 bg-emerald-950/20 p-3 text-sm text-slate-300">
            <p>{finding.enrichment.note}</p>
            {!!finding.enrichment.corroborating_datasets?.length && (
              <p className="mt-1 text-[11px] text-slate-500">
                Corroborated by:{" "}
                {finding.enrichment.corroborating_datasets
                  .map((d) => d.filename ?? `dataset ${d.id}`)
                  .join(", ")}
              </p>
            )}
          </div>
        </Field>
      )}

      <Field label="Evidence">
        <pre className="max-h-72 overflow-auto rounded border border-slate-800 bg-slate-950 p-3 font-mono text-xs text-slate-300">
          {prettyJson(finding.evidence)}
        </pre>
      </Field>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="MITRE ATT&CK">
          <Pills items={asList(finding.mitre)} />
        </Field>
        <Field label="Recommendations">
          {asList(finding.recommendations).length > 0 ? (
            <ul className="list-inside list-disc space-y-1 text-sm text-slate-300">
              {asList(finding.recommendations).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-600">—</p>
          )}
        </Field>
        <Field label="Affected Assets">
          <Pills items={asList(finding.affected_assets)} />
        </Field>
        <Field label="Affected Users">
          <Pills items={asList(finding.affected_users)} />
        </Field>
      </div>

      <Field label="Reviewer Notes">
        <Textarea
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Persistent annotation — saved with the finding and fed to the knowledge base on accept."
        />
        <div className="mt-2">
          <Button
            variant="ghost"
            disabled={patching || !notesDirty}
            onClick={() => onPatch({ reviewer_notes: notes })}
          >
            Save notes
          </Button>
        </div>
      </Field>

      {/* Disposition (W1): every action teaches the model — feedback + 1–10 score.
          Accept/reject record the verdict; partial rewrites the finding and lets
          you iterate until it's right, then accept. */}
      <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Disposition</span>
          {finding.disposition && (
            <span className="text-[11px] text-slate-400">
              current: <b className="text-slate-300">{finding.disposition}</b>
              {finding.score ? ` · ${finding.score}/10` : ""}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant={mode === "accept" ? "success" : "ghost"}
            disabled={patching}
            onClick={() => { setMode(mode === "accept" ? null : "accept"); setFeedback(""); setScore(null); }}
          >
            Accept
          </Button>
          <Button
            variant={mode === "partial" ? "primary" : "ghost"}
            disabled={patching}
            onClick={() => { setMode(mode === "partial" ? null : "partial"); setFeedback(""); setScore(null); }}
          >
            Partial — fix &amp; retry
          </Button>
          <Button
            variant={mode === "reject" ? "danger" : "ghost"}
            disabled={patching}
            onClick={() => { setMode(mode === "reject" ? null : "reject"); setFeedback(""); setScore(null); }}
          >
            Reject
          </Button>
        </div>

        {mode && (
          <div className="mt-3 space-y-2">
            <Textarea
              rows={2}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder={
                mode === "accept"
                  ? "Optional: why is this a good finding? (teaches the model what 'good' looks like)"
                  : mode === "partial"
                  ? "Required: what's missing or wrong? The model rewrites the finding to address this."
                  : "Required: why is this a false positive / not reportable?"
              }
            />
            {mode !== "partial" && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-[11px] uppercase tracking-wide text-slate-500">Score</span>
                {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setScore(score === n ? null : n)}
                    className={`h-6 w-6 rounded text-xs ${score === n ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {mode === "accept" && (
                <Button
                  variant="success"
                  disabled={patching}
                  onClick={async () => {
                    const r = await onDispose("accept", feedback || undefined, score ?? undefined);
                    setReflection(r);
                    setMode(null);
                  }}
                >
                  {patching ? <Spinner /> : "Confirm accept"}
                </Button>
              )}
              {mode === "partial" && (
                <Button
                  variant="primary"
                  disabled={patching || !feedback.trim()}
                  onClick={async () => {
                    const r = await onRegenerate(feedback);
                    if (r) setRevision(r);
                  }}
                >
                  {patching ? <Spinner /> : "Regenerate from feedback"}
                </Button>
              )}
              {mode === "reject" && (
                <>
                  <Button
                    variant="danger"
                    disabled={patching || !feedback.trim()}
                    onClick={async () => {
                      const r = await onDispose("reject", feedback, score ?? undefined);
                      setReflection(r);
                      setMode(null);
                    }}
                  >
                    {patching ? <Spinner /> : "Confirm reject"}
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={patching}
                    onClick={() => {
                      if (window.confirm("Delete this finding permanently? It is removed everywhere, including the knowledge base.")) {
                        onDelete();
                      }
                    }}
                  >
                    Delete permanently
                  </Button>
                </>
              )}
              <Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button>
            </div>
            {mode === "partial" && (
              <p className="text-[11px] text-slate-500">
                Regenerate as many times as needed — each round is recorded. When it’s right, switch to Accept.
              </p>
            )}
          </div>
        )}

        {reflection && (
          <div className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.05] p-3">
            <div className="mb-1 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-300">
                What the model learned from your feedback
              </p>
              <button onClick={() => setReflection(null)} className="text-xs text-slate-500 hover:text-slate-300">
                Dismiss
              </button>
            </div>
            <p className="text-sm leading-relaxed text-slate-200">{reflection.lesson}</p>
            {reflection.reasoning && (
              <p className="mt-1 text-xs text-slate-400">{reflection.reasoning}</p>
            )}
            <p className="mt-2 text-[11px] text-slate-500">
              Saved to this client's knowledge base — it informs the next hunt's analysis (no retraining).
            </p>
          </div>
        )}

        {revision && <RevisionResultPanel revision={revision} onDismiss={() => setRevision(null)} />}
      </div>
    </div>
  );
}

/** What the model did on a partial-accept regeneration: reasoning, a per-point
 *  checklist, and the before→after diff — so the action is never invisible. */
function RevisionResultPanel({
  revision,
  onDismiss,
}: {
  revision: FindingRevisionResult;
  onDismiss: () => void;
}) {
  const fmt = (v: unknown) =>
    v == null || v === "" ? "—" : typeof v === "string" ? v : JSON.stringify(v);
  return (
    <div className="mt-3 rounded-lg border border-indigo-500/30 bg-indigo-500/[0.05] p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-300">
          What the model did{revision.no_op ? " — no change" : ""}
        </p>
        <button onClick={onDismiss} className="text-xs text-slate-500 hover:text-slate-300">
          Dismiss
        </button>
      </div>

      {revision.reasoning && (
        <p className="mb-3 text-sm leading-relaxed text-slate-300">{revision.reasoning}</p>
      )}

      {revision.addressed.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Your feedback, point by point
          </p>
          <ul className="space-y-1.5">
            {revision.addressed.map((a, i) => (
              <li key={i} className="flex gap-2 text-sm">
                <span className={a.addressed ? "text-emerald-400" : "text-amber-400"}>
                  {a.addressed ? "✓" : "✗"}
                </span>
                <span className="text-slate-300">
                  <b className="text-slate-200">{a.point}</b>
                  {a.how && <span className="text-slate-400"> — {a.how}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {revision.changes.length > 0 ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Changed fields ({revision.changes.length})
          </p>
          <ul className="space-y-1.5">
            {revision.changes.map((c, i) => (
              <li key={i} className="rounded border border-slate-800 bg-slate-950/50 p-2 text-xs">
                <span className="font-mono uppercase tracking-wide text-slate-500">{c.field}</span>
                <div className="mt-1 flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-2">
                  <span className="text-rose-300/90 line-through">{fmt(c.before)}</span>
                  <span className="hidden text-slate-600 sm:inline">→</span>
                  <span className="text-emerald-300">{fmt(c.after)}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-xs text-slate-500">
          No fields were changed — the model kept the finding as-is for the reason above.
        </p>
      )}
    </div>
  );
}

export default function FindingsPanel({
  tid,
  hid,
  reloadKey,
}: {
  tid: string;
  hid: string;
  reloadKey: number;
}) {
  const toast = useToast();
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [patchingId, setPatchingId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [showMerged, setShowMerged] = useState(false);

  // After correlation, merged findings are folded into their survivor. Hide them
  // by default so this tab shows the curated, post-correlation list.
  const mergedCount = (findings ?? []).filter((f) => f.merged_into_id != null).length;
  const visible =
    findings === null
      ? null
      : showMerged
        ? findings
        : findings.filter((f) => f.merged_into_id == null);

  const load = () =>
    api
      .listFindings(tid, hid)
      .then((f) => {
        setFindings(f);
        setSelected(new Set());
      })
      .catch((e: ApiError) => {
        toast.error(e.message);
        setFindings([]);
      });

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid, hid, reloadKey]);

  const onPatch = async (finding: Finding, body: PatchBody) => {
    setPatchingId(finding.id);
    try {
      const updated = await api.patchFinding(tid, hid, finding.id, body);
      setFindings((prev) =>
        prev ? prev.map((f) => (f.id === finding.id ? { ...f, ...updated } : f)) : prev,
      );
      toast.success(body.status ? `Finding ${body.status}.` : "Notes saved.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Update failed.");
    } finally {
      setPatchingId(null);
    }
  };

  const onDispose = async (
    finding: Finding,
    action: "accept" | "reject" | "partial",
    feedback?: string,
    score?: number,
  ): Promise<DispositionReflection | null> => {
    setPatchingId(finding.id);
    try {
      const result = await api.dispositionFinding(tid, hid, finding.id, { action, feedback, score });
      setFindings((prev) =>
        prev ? prev.map((f) => (f.id === finding.id ? { ...f, ...result.finding } : f)) : prev,
      );
      toast.success(`Finding ${action}ed${score ? ` · ${score}/10` : ""}.`);
      return result.reflection;
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Disposition failed.");
      return null;
    } finally {
      setPatchingId(null);
    }
  };

  const onRegenerate = async (
    finding: Finding,
    feedback: string,
  ): Promise<FindingRevisionResult | null> => {
    setPatchingId(finding.id);
    try {
      const result = await api.regenerateFinding(tid, hid, finding.id, feedback);
      setFindings((prev) =>
        prev ? prev.map((f) => (f.id === finding.id ? { ...f, ...result.finding } : f)) : prev,
      );
      if (result.no_op) toast.info("Model reviewed it and made no change — see its reasoning below.");
      else toast.success(`Regenerated — ${result.changes.length} field(s) changed. Review and accept, or refine again.`);
      return result;
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Regeneration failed.");
      return null;
    } finally {
      setPatchingId(null);
    }
  };

  const onDelete = async (finding: Finding) => {
    setPatchingId(finding.id);
    try {
      await api.deleteFinding(tid, hid, finding.id);
      setFindings((prev) => (prev ? prev.filter((f) => f.id !== finding.id) : prev));
      setExpanded(null);
      toast.success("Finding deleted.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Delete failed.");
    } finally {
      setPatchingId(null);
    }
  };

  const bulkDelete = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(`Delete ${selected.size} finding(s) permanently?`)) return;
    setBulkBusy(true);
    try {
      await Promise.all([...selected].map((id) => api.deleteFinding(tid, hid, id)));
      setFindings((prev) => (prev ? prev.filter((f) => !selected.has(f.id)) : prev));
      setSelected(new Set());
      toast.success("Findings deleted.");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Bulk delete failed.");
    } finally {
      setBulkBusy(false);
    }
  };

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const toggleAll = () => {
    if (!visible) return;
    setSelected((prev) =>
      prev.size === visible.length ? new Set() : new Set(visible.map((f) => f.id)),
    );
  };

  return (
    <Card>
      <PanelHeader
        title="Findings"
        subtitle="Curated findings — correlation results applied (merges, enrichment, chains)"
        right={
          findings ? (
            <div className="flex items-center gap-3 text-xs text-slate-500">
              <span>
                {visible?.length ?? 0} shown
                {mergedCount ? ` · ${mergedCount} merged` : ""}
              </span>
              {mergedCount > 0 && (
                <button
                  onClick={() => setShowMerged((s) => !s)}
                  className="rounded border border-slate-700 px-2 py-0.5 text-slate-300 hover:bg-slate-800"
                >
                  {showMerged ? "Hide merged" : "Show merged"}
                </button>
              )}
            </div>
          ) : null
        }
      />

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-950/40 px-4 py-2.5">
          <span className="text-xs text-slate-400">{selected.size} selected</span>
          {/* Accept / reject is per-finding only (with feedback) — see each finding's
              detail panel. Bulk disposition without feedback was removed by design. */}
          <Button variant="danger" disabled={bulkBusy} onClick={bulkDelete}>
            {bulkBusy ? <Spinner /> : "Delete selected"}
          </Button>
          <Button variant="ghost" disabled={bulkBusy} onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        </div>
      )}

      <div className="p-4">
        <MissedFindingWizard tid={tid} hid={hid} onAdded={load} />
        {findings === null ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : findings.length === 0 ? (
          <EmptyState>
            No findings yet. Upload and analyze a dataset to generate findings, or add one
            the hunt missed above.
          </EmptyState>
        ) : (visible?.length ?? 0) === 0 ? (
          <EmptyState>
            All findings were merged during correlation. Use “Show merged” to view them.
          </EmptyState>
        ) : (
          <div className="overflow-hidden rounded border border-slate-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/40 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Select all"
                      checked={(visible?.length ?? 0) > 0 && selected.size === (visible?.length ?? 0)}
                      onChange={toggleAll}
                    />
                  </th>
                  <th className="px-3 py-2 font-medium">Ref</th>
                  <th className="px-3 py-2 font-medium">Title</th>
                  <th className="px-3 py-2 font-medium">Category</th>
                  <th className="px-3 py-2 font-medium">Severity</th>
                  <th className="px-3 py-2 font-medium">Confidence</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {(visible ?? []).map((f) => {
                  const open = expanded === f.id;
                  return (
                    <Fragment key={f.id}>
                      <tr
                        onClick={() => setExpanded(open ? null : f.id)}
                        className={`cursor-pointer border-b border-slate-900 transition-colors hover:bg-slate-800/40 ${
                          open ? "bg-slate-800/40" : ""
                        }`}
                      >
                        <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            aria-label={`Select ${f.finding_ref}`}
                            checked={selected.has(f.id)}
                            onChange={() => toggle(f.id)}
                          />
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-indigo-300">
                          {f.finding_ref}
                        </td>
                        <td className="px-3 py-2.5 text-slate-200">
                          <span className={f.merged_into_id ? "text-slate-500 line-through" : ""}>
                            {f.title}
                          </span>
                          <span className="ml-2 inline-flex gap-1 align-middle">
                            {f.chain_id != null && (
                              <span className="rounded bg-indigo-900/50 px-1.5 py-0.5 text-[10px] text-indigo-200">
                                chain
                              </span>
                            )}
                            {f.enrichment?.note && (
                              <span className="rounded bg-emerald-900/40 px-1.5 py-0.5 text-[10px] text-emerald-200">
                                enriched
                              </span>
                            )}
                            {f.merged_into_id != null && (
                              <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                                merged
                              </span>
                            )}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <CategoryBadge category={f.category} />
                        </td>
                        <td className="px-3 py-2.5 text-xs text-slate-400">
                          {f.severity ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-slate-400">
                          {f.confidence != null ? String(f.confidence) : "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <FindingStatusBadge status={f.status} />
                        </td>
                      </tr>
                      {open && (
                        <tr>
                          <td colSpan={7} className="p-0">
                            <FindingDetail
                              finding={f}
                              patching={patchingId === f.id}
                              onPatch={(body) => onPatch(f, body)}
                              onDispose={(action, feedback, score) => onDispose(f, action, feedback, score)}
                              onRegenerate={(feedback) => onRegenerate(f, feedback)}
                              onDelete={() => onDelete(f)}
                            />
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
  );
}
