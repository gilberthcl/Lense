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

function asList(value: unknown): string[] {
  if (value == null) return [];
  if (Array.isArray(value)) return value.map((v) => String(v));
  if (typeof value === "string") {
    const trimmed = value.trim();
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed.map((v) => String(v));
    } catch {
      // fall through
    }
    return trimmed ? [trimmed] : [];
  }
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
  patching,
}: {
  finding: Finding;
  onPatch: (body: PatchBody) => void;
  patching: boolean;
}) {
  const [notes, setNotes] = useState(finding.reviewer_notes ?? "");
  const notesDirty = notes !== (finding.reviewer_notes ?? "");
  return (
    <div className="space-y-4 border-t border-slate-800 bg-slate-950/60 p-4">
      {finding.summary && (
        <Field label="Summary">
          <p className="whitespace-pre-wrap text-sm text-slate-300">
            {finding.summary}
          </p>
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
        <Button
          variant="danger"
          disabled={patching || finding.status === "rejected"}
          onClick={() => onPatch({ status: "rejected" })}
        >
          Reject
        </Button>
      </div>
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

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const toggleAll = () => {
    if (!findings) return;
    setSelected((prev) =>
      prev.size === findings.length ? new Set() : new Set(findings.map((f) => f.id)),
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
        subtitle="AI-generated findings — review, validate, or reject"
        right={
          findings ? (
            <span className="text-xs text-slate-500">
              {findings.length} total
            </span>
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
        ) : (
          <div className="overflow-hidden rounded border border-slate-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/40 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Select all"
                      checked={findings.length > 0 && selected.size === findings.length}
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
                {findings.map((f) => {
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
                        <td className="px-3 py-2.5 text-slate-200">{f.title}</td>
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
