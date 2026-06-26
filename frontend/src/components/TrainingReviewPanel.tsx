import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Hunt, TrainingReviewState } from "../lib/types";
import { useToast } from "./Toast";
import { Badge, Button, Card, EmptyState, PanelHeader, Spinner, Textarea } from "./ui";

/**
 * Training-hunt "what I learned" review (W3).
 *
 * For a historic training hunt: the model studies the confirmed findings + the
 * datasets and articulates the detection logic it learned. The analyst then
 * accepts (the lesson informs future hunts), rejects, or regenerates with
 * feedback. This is the learning core of a training hunt.
 */
export default function TrainingReviewPanel({
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
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedback, setFeedback] = useState("");

  const review: TrainingReviewState | null = hunt?.training_review ?? null;
  const report = review?.report ?? null;
  const disposition = review?.disposition ?? null;

  const run = async (fb?: string) => {
    setBusy(true);
    setStage(fb ? "Revising what was learned with your feedback…" : "Studying findings + datasets to learn the detection logic…");
    try {
      await api.runTrainingReview(tid, hid, fb);
      onRefresh();
      toast.success(fb ? "Review revised." : "Review ready — confirm what the model learned.");
      setShowFeedback(false);
      setFeedback("");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Review failed.");
    } finally {
      setBusy(false);
      setStage("");
    }
  };

  const dispose = async (action: "accept" | "reject", fb?: string) => {
    setBusy(true);
    try {
      await api.disposeTrainingReview(tid, hid, action, fb);
      onRefresh();
      toast.success(
        action === "accept"
          ? "Accepted — this detection logic now informs future hunts for this client."
          : "Rejected — it won't inform future hunts.",
      );
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Update failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <PanelHeader
        title="What the model learned"
        subtitle="The detection logic the model took from this training hunt's findings + datasets — confirm it, correct it, or regenerate"
        right={
          <div className="flex items-center gap-2">
            {disposition && (
              <Badge
                className={
                  disposition === "accepted"
                    ? "border border-emerald-800 bg-emerald-950 text-emerald-300"
                    : "border border-rose-800 bg-rose-950 text-rose-300"
                }
              >
                {disposition}
              </Badge>
            )}
            <Button onClick={() => run()} disabled={busy}>
              {busy ? <Spinner /> : report ? "Re-analyze" : "Analyze what was learned"}
            </Button>
          </div>
        }
      />
      <div className="space-y-4 p-4">
        {busy && stage && (
          <div className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-400">
            <Spinner /> {stage}
          </div>
        )}

        {!report && !busy && (
          <EmptyState>
            Add this hunt's known findings (and its datasets), then click “Analyze what was learned”.
            The model studies them and explains the detection logic it learned — you confirm or correct it.
          </EmptyState>
        )}

        {report && (
          <>
            {report.overview && (
              <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/[0.04] p-3">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-indigo-300/80">
                  Detection logic learned
                </p>
                <p className="text-sm leading-relaxed text-slate-300">{report.overview}</p>
              </div>
            )}

            {report.patterns.length > 0 && (
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Patterns ({report.patterns.length})
                </p>
                <ul className="space-y-2">
                  {report.patterns.map((p, i) => (
                    <li key={i} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-slate-200">{p.name}</span>
                        {p.category && (
                          <Badge className="border border-slate-700 bg-slate-800 text-slate-300">{p.category}</Badge>
                        )}
                      </div>
                      {p.signal && (
                        <p className="mt-1 text-xs text-slate-400">
                          <span className="text-slate-500">Signal: </span>{p.signal}
                        </p>
                      )}
                      {p.rationale && (
                        <p className="mt-1 text-xs text-slate-400">
                          <span className="text-slate-500">Why: </span>{p.rationale}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {report.false_positive_lessons.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Benign look-alikes (false-positive lessons)
                </p>
                <ul className="list-inside list-disc space-y-0.5 text-sm text-slate-300">
                  {report.false_positive_lessons.map((fp, i) => <li key={i}>{fp}</li>)}
                </ul>
              </div>
            )}

            {report.takeaways.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Takeaways for future hunts
                </p>
                <ul className="list-inside list-disc space-y-0.5 text-sm text-slate-300">
                  {report.takeaways.map((t, i) => <li key={i}>{t}</li>)}
                </ul>
              </div>
            )}

            {/* Accept / reject / regenerate-with-feedback */}
            {disposition !== "accepted" && (
              <div className="flex flex-wrap items-center gap-2 border-t border-slate-800 pt-3">
                <Button variant="success" disabled={busy} onClick={() => dispose("accept")}>
                  {busy ? <Spinner /> : "Accept — this is right"}
                </Button>
                <Button
                  variant={showFeedback ? "primary" : "ghost"}
                  disabled={busy}
                  onClick={() => setShowFeedback((s) => !s)}
                >
                  Regenerate with feedback
                </Button>
                <Button variant="danger" disabled={busy} onClick={() => dispose("reject")}>
                  Reject
                </Button>
              </div>
            )}

            {showFeedback && (
              <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/[0.05] p-3">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-indigo-300">
                  What did the model get wrong?
                </p>
                <Textarea
                  rows={3}
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  placeholder="e.g. Pattern 2 isn't malicious here — it's the approved backup agent. You missed the persistence logic in the scheduled-task dataset."
                />
                <div className="mt-2 flex justify-end gap-2">
                  <Button variant="ghost" onClick={() => { setShowFeedback(false); setFeedback(""); }}>
                    Cancel
                  </Button>
                  <Button variant="primary" disabled={busy || !feedback.trim()} onClick={() => run(feedback.trim())}>
                    {busy ? <Spinner /> : "Regenerate with this feedback"}
                  </Button>
                </div>
              </div>
            )}

            {disposition === "accepted" && (
              <p className="border-t border-slate-800 pt-3 text-[11px] text-emerald-300/80">
                Accepted — saved to this client's knowledge base. It informs the next hunt's analysis
                (no retraining). You can “Complete training” to move this hunt to the previous hunts.
              </p>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
