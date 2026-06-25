import { Fragment, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Finding, FindingStatus } from "../lib/types";
import { useToast } from "./Toast";
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
  onDelete,
  patching,
}: {
  finding: Finding;
  onPatch: (body: PatchBody) => void;
  onDelete: () => void;
  patching: boolean;
}) {
  const [notes, setNotes] = useState(finding.reviewer_notes ?? "");
  const notesDirty = notes !== (finding.reviewer_notes ?? "");
  const [rejecting, setRejecting] = useState(false);
  const [feedback, setFeedback] = useState("");
  return (
    <div className="space-y-4 border-t border-slate-800 bg-slate-950/60 p-4">
      {finding.summary && (
        <Field label="Summary">
          <p className="whitespace-pre-wrap text-sm text-slate-300">
            {finding.summary}
          </p>
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
          placeholder="Add review rationale — saved with the finding and fed to the knowledge base on validation."
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

      <div className="flex items-center gap-2 pt-1">
        <Button
          variant="success"
          disabled={patching || finding.status === "validated"}
          onClick={() => onPatch({ status: "validated" })}
        >
          {patching ? <Spinner /> : "Validate"}
        </Button>
        <Button variant="danger" disabled={patching} onClick={() => setRejecting((s) => !s)}>
          Reject…
        </Button>
      </div>

      {rejecting && (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Reject this finding
          </p>
          <Textarea
            rows={2}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Optional feedback — why it's a false positive / what's wrong. Saved with the rejection."
          />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button
              variant="ghost"
              disabled={patching}
              onClick={() => {
                onPatch({ status: "rejected", reviewer_notes: feedback || notes });
                setRejecting(false);
              }}
            >
              Reject &amp; keep feedback
            </Button>
            <Button
              variant="danger"
              disabled={patching}
              onClick={() => {
                if (window.confirm("Delete this finding permanently? It is removed everywhere, including the knowledge base.")) {
                  onDelete();
                }
              }}
            >
              Delete permanently
            </Button>
            <Button variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button>
          </div>
        </div>
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

  const bulk = async (status: FindingStatus) => {
    if (selected.size === 0) return;
    setBulkBusy(true);
    try {
      const updated = await api.bulkPatchFindings(tid, hid, [...selected], status);
      const byId = new Map(updated.map((u) => [u.id, u]));
      setFindings((prev) =>
        prev ? prev.map((f) => (byId.has(f.id) ? { ...f, ...byId.get(f.id)! } : f)) : prev,
      );
      toast.success(`${updated.length} finding(s) ${status}.`);
      setSelected(new Set());
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Bulk update failed.");
    } finally {
      setBulkBusy(false);
    }
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
          <Button variant="success" disabled={bulkBusy} onClick={() => bulk("validated")}>
            {bulkBusy ? <Spinner /> : "Validate selected"}
          </Button>
          <Button variant="danger" disabled={bulkBusy} onClick={() => bulk("rejected")}>
            Reject selected
          </Button>
          <Button variant="danger" disabled={bulkBusy} onClick={bulkDelete}>
            {bulkBusy ? <Spinner /> : "Delete selected"}
          </Button>
          <Button variant="ghost" disabled={bulkBusy} onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        </div>
      )}

      <div className="p-4">
        {findings === null ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : findings.length === 0 ? (
          <EmptyState>
            No findings yet. Upload and analyze a dataset to generate findings.
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
