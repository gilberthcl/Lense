import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { useToast } from "./Toast";
import { Button, Spinner, Textarea } from "./ui";

/**
 * Reusable per-stage learning feedback (W4). Drop into any stage panel:
 *   <StageFeedback tid={tid} hid={hid} stage="qa" label="QA" />
 * Records disposition + 1–10 score + feedback; the lesson mirrors into RAG.
 */
export default function StageFeedback({
  tid,
  hid,
  stage,
  label,
  onRecorded,
}: {
  tid: string;
  hid: string;
  stage: string;
  label?: string;
  onRecorded?: () => void;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [score, setScore] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (disposition: string) => {
    if (!feedback.trim() && score === null) {
      toast.error("Add feedback or a score.");
      return;
    }
    setBusy(true);
    try {
      await api.stageFeedback(tid, hid, stage, {
        disposition,
        score: score ?? undefined,
        feedback: feedback.trim() || undefined,
      });
      toast.success(`Recorded — teaches the ${label ?? stage} stage.`);
      setFeedback("");
      setScore(null);
      setOpen(false);
      onRecorded?.();
    } catch (e) {
      toast.error((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => setOpen(true)}>
        Rate this stage
      </Button>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Rate the {label ?? stage} stage — teaches the model
      </p>
      <Textarea
        rows={2}
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder={`What did the ${label ?? stage} stage do well or poorly? This becomes a lesson.`}
      />
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
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
      <div className="mt-2 flex flex-wrap gap-2">
        <Button variant="success" disabled={busy} onClick={() => submit("accepted")}>
          {busy ? <Spinner /> : "Good"}
        </Button>
        <Button variant="primary" disabled={busy} onClick={() => submit("needs_work")}>
          Needs work
        </Button>
        <Button variant="danger" disabled={busy} onClick={() => submit("rejected")}>
          Poor
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </div>
  );
}
