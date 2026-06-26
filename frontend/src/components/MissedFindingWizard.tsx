import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Dataset, MissedFindingResult } from "../lib/types";
import { useToast } from "./Toast";
import { Button, Spinner, Textarea } from "./ui";

/**
 * Missed-finding wizard (W2) — false-negative capture.
 *
 * The analyst pastes a finding they found manually that the automated pass
 * missed, plus the dataset it came from. The model reconstructs the structured
 * finding, diagnoses why it was missed, and the lesson is mirrored into RAG.
 */
export default function MissedFindingWizard({
  tid,
  hid,
  onAdded,
}: {
  tid: string;
  hid: string;
  onAdded: () => void;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<MissedFindingResult | null>(null);
  const [context, setContext] = useState("");
  const [savingContext, setSavingContext] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.listDatasets(tid, hid).then(setDatasets).catch(() => setDatasets([]));
  }, [open, tid, hid]);

  const submit = async () => {
    if (!datasetId || !description.trim()) {
      toast.error("Pick the dataset and describe the finding.");
      return;
    }
    setSubmitting(true);
    setResult(null);
    try {
      const r = await api.addMissedFinding(tid, hid, datasetId, description);
      setResult(r);
      setContext("");
      toast.success(`Added ${r.finding.finding_ref} — the model explained why it was missed.`);
      onAdded();
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setSubmitting(false);
    }
  };

  const saveContext = async () => {
    if (!result || !context.trim()) return;
    setSavingContext(true);
    try {
      await api.addMissedContext(tid, hid, result.finding.id, context);
      toast.success("Context saved — it feeds the model's learning.");
      setContext("");
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setSavingContext(false);
    }
  };

  const reset = () => {
    setDescription("");
    setDatasetId("");
    setResult(null);
    setContext("");
  };

  if (!open) {
    return (
      <div className="mb-3">
        <Button variant="ghost" onClick={() => setOpen(true)}>
          + Add a finding the hunt missed
        </Button>
      </div>
    );
  }

  return (
    <div className="mb-3 rounded-lg border border-slate-800 bg-slate-950/60 p-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Add a missed finding
        </p>
        <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => { setOpen(false); reset(); }}>
          Close
        </Button>
      </div>

      <div className="space-y-2">
        <label className="block text-xs text-slate-400">
          Dataset it was found in
          <select
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          >
            <option value="">Select a dataset…</option>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>{d.filename}</option>
            ))}
          </select>
        </label>
        <Textarea
          rows={4}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe the finding you found manually — what it is, the hosts/users/values involved, and why it matters. Paste details freely."
        />
        <Button variant="primary" disabled={submitting} onClick={submit}>
          {submitting ? <Spinner /> : "Analyse & add"}
        </Button>
      </div>

      {result && (
        <div className="mt-4 space-y-3 border-t border-slate-800 pt-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-300">
              Added {result.finding.finding_ref}: {result.finding.title}
            </p>
          </div>
          {result.why_missed && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Why it was missed</p>
              <p className="text-sm text-slate-300">{result.why_missed}</p>
            </div>
          )}
          {result.lessons && (
            <div>
              <p className="text-[11px] uppercase tracking-wide text-slate-500">Lessons learned</p>
              <p className="text-sm text-slate-300">{result.lessons}</p>
            </div>
          )}
          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
              Add more context (optional — enriches the lesson)
            </p>
            <Textarea
              rows={2}
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="Anything to add about why this matters or how to catch it next time…"
            />
            <div className="mt-2 flex gap-2">
              <Button variant="ghost" disabled={savingContext || !context.trim()} onClick={saveContext}>
                {savingContext ? <Spinner /> : "Save context"}
              </Button>
              <Button variant="ghost" onClick={reset}>Add another</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
