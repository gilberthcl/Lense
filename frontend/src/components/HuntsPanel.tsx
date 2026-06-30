import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { CreateHuntInput, Hunt } from "../lib/types";
import { useToast } from "./Toast";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  fmtDate,
  Input,
  Label,
  PanelHeader,
  Select,
  Spinner,
  Textarea,
} from "./ui";

const EMPTY_FORM: CreateHuntInput = {
  name: "",
  objective: "",
  methodology_text: "",
  report_language: "English",
  edr: "",
  siem: "",
};

export default function HuntsPanel({
  tid,
  clientBase = "/clients",
}: {
  tid: string;
  /** Path prefix for in-context links, e.g. /clients or /structured-hunts/clients */
  clientBase?: string;
}) {
  const toast = useToast();
  const [hunts, setHunts] = useState<Hunt[] | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showReportForm, setShowReportForm] = useState(false);
  const [reportFile, setReportFile] = useState<File | null>(null);
  const [reportMeta, setReportMeta] = useState({ name: "", edr: "", siem: "", report_language: "English" });
  const [listTab, setListTab] = useState<"live" | "historic" | "training">("live");
  const [formKind, setFormKind] = useState<"live" | "training">("live");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState<CreateHuntInput>(EMPTY_FORM);

  const openForm = (kind: "live" | "training") => {
    setFormKind(kind);
    setForm({ ...EMPTY_FORM, kind });
    setShowForm(true);
  };
  const [methodFile, setMethodFile] = useState<File | null>(null);

  const load = () =>
    api
      .listHunts(tid)
      .then(setHunts)
      .catch((e: ApiError) => {
        toast.error(e.message);
        setHunts([]);
      });

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error("Hunt name is required.");
    setSubmitting(true);
    try {
      const hunt = await api.createHunt(tid, {
        name: form.name.trim(),
        objective: form.objective?.trim() || undefined,
        methodology_text: form.methodology_text?.trim() || undefined,
        report_language: form.report_language || "English",
        edr: form.edr?.trim() || undefined,
        siem: form.siem?.trim() || undefined,
        kind: formKind,
      });
      // If a methodology file was provided, upload it and kick off comprehension.
      if (methodFile) {
        await api.uploadMethodology(tid, hunt.id, methodFile);
      }
      const hasMethodology = !!methodFile || !!form.methodology_text?.trim();
      if (hasMethodology) {
        api.analyzeMethodology(tid, hunt.id).catch(() => undefined); // background
        toast.success("Hunt created — comprehending methodology…");
      } else {
        toast.success("Hunt created.");
      }
      setForm(EMPTY_FORM);
      setMethodFile(null);
      setShowForm(false);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to create hunt.");
    } finally {
      setSubmitting(false);
    }
  };

  const openReportForm = () => {
    setReportMeta({ name: "", edr: "", siem: "", report_language: "English" });
    setReportFile(null);
    setMethodFile(null);
    setShowForm(false);
    setShowReportForm(true);
  };

  const onSubmitReport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reportFile) return toast.error("Upload the final hunt report (.docx).");
    setSubmitting(true);
    try {
      const r = await api.createHuntFromReport(tid, {
        report: reportFile,
        methodology: methodFile,
        name: reportMeta.name.trim() || undefined,
        edr: reportMeta.edr.trim() || undefined,
        siem: reportMeta.siem.trim() || undefined,
        report_language: reportMeta.report_language,
      });
      toast.success(
        `Training hunt created from report — ${r.findings_loaded} finding(s) loaded` +
          `${r.has_methodology ? ", methodology set" : ""}${r.has_mitre ? ", MITRE coverage parsed" : ""}. ` +
          "Now upload the datasets to analyze.",
      );
      setShowReportForm(false);
      setReportFile(null);
      setMethodFile(null);
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not parse the report.");
    } finally {
      setSubmitting(false);
    }
  };

  const liveHunts = (hunts ?? []).filter((h) => h.kind !== "training" && h.status !== "completed");
  // Completed hunts — live or training — move to Historic ("previous hunts").
  const historicHunts = (hunts ?? []).filter((h) => h.status === "completed");
  const trainingHunts = (hunts ?? []).filter((h) => h.kind === "training" && h.status !== "completed");

  const setHuntStatus = async (h: Hunt, complete: boolean) => {
    const training = h.kind === "training";
    try {
      await (complete ? api.completeHunt(tid, h.id) : api.reopenHunt(tid, h.id));
      toast.success(
        complete
          ? training
            ? "Training complete — moved to previous hunts."
            : "Hunt completed — moved to Historic."
          : "Hunt reopened.",
      );
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed.");
    }
  };

  const TABS: { id: "live" | "historic" | "training"; label: string; list: Hunt[] }[] = [
    { id: "live", label: `Live (${liveHunts.length})`, list: liveHunts },
    { id: "historic", label: `Historic (${historicHunts.length})`, list: historicHunts },
    { id: "training", label: `Training (${trainingHunts.length})`, list: trainingHunts },
  ];
  const active = TABS.find((t) => t.id === listTab) ?? TABS[0];

  return (
    <Card>
      <PanelHeader
        title="Hunts"
        subtitle="Hypothesis-driven hunt runs scoped to this client"
        right={
          showForm || showReportForm ? (
            <Button variant="ghost" onClick={() => { setShowForm(false); setShowReportForm(false); }}>
              Close
            </Button>
          ) : (
            <div className="flex items-center gap-2">
              <Button onClick={() => openForm("live")}>+ New Hunt</Button>
              <Button variant="ghost" onClick={() => openForm("training")}>+ Training Hunt</Button>
              <Button variant="ghost" onClick={openReportForm}>+ From Report</Button>
            </div>
          )
        }
      />

      {showForm && (
        <div className="border-b border-slate-800 bg-slate-950/40 px-4 pt-3 text-xs text-slate-400">
          {formKind === "training" ? (
            <span className="text-amber-300">
              Creating a <b>Historic Training Hunt</b> — its findings become training data for this
              client's model, not a live deliverable.
            </span>
          ) : (
            <span>Creating a new live hunt.</span>
          )}
        </div>
      )}

      {showForm && (
        <form
          onSubmit={onSubmit}
          className="space-y-3 border-b border-slate-800 bg-slate-950/40 p-4"
        >
          <div>
            <Label>Name</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Suspicious PowerShell — Q2"
            />
          </div>
          <div>
            <Label>Objective</Label>
            <Textarea
              rows={2}
              value={form.objective ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, objective: e.target.value }))
              }
              placeholder="What hypothesis is this hunt testing?"
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <Label>Report Language</Label>
              <Select
                value={form.report_language ?? "English"}
                onChange={(e) =>
                  setForm((f) => ({ ...f, report_language: e.target.value }))
                }
              >
                <option value="English">English</option>
                <option value="Spanish">Spanish</option>
              </Select>
            </div>
            <div>
              <Label>EDR</Label>
              <Input
                value={form.edr ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, edr: e.target.value }))}
                placeholder="e.g. CrowdStrike Falcon"
              />
            </div>
            <div>
              <Label>SIEM</Label>
              <Input
                value={form.siem ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, siem: e.target.value }))}
                placeholder="e.g. IBM QRadar"
              />
            </div>
          </div>
          <div>
            <Label>Methodology — upload (.docx / .txt / .md)</Label>
            <input
              type="file"
              accept=".docx,.txt,.md,.markdown"
              onChange={(e) => setMethodFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-md file:border file:border-slate-700 file:bg-slate-800 file:px-3 file:py-1.5 file:text-sm file:text-slate-200 hover:file:bg-slate-700"
            />
            {methodFile && (
              <p className="mt-1 text-xs text-slate-500">Selected: {methodFile.name}</p>
            )}
          </div>
          <div>
            <Label>Methodology — or paste text</Label>
            <Textarea
              rows={4}
              value={form.methodology_text ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, methodology_text: e.target.value }))
              }
              placeholder="Paste the hunt methodology, or leave blank if uploading a file (or to inherit the client's methodology)."
              className="font-mono text-xs"
            />
          </div>
          <p className="text-xs text-slate-600">
            The engine fully comprehends the methodology — plan of action and
            executed queries — before analyzing any dataset.
          </p>
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? <Spinner /> : (formKind === "training" ? "Create Training Hunt" : "Create Hunt")}
          </Button>
        </form>
      )}

      {showReportForm && (
        <form onSubmit={onSubmitReport} className="space-y-3 border-b border-slate-800 bg-slate-950/40 p-4">
          <p className="text-xs text-amber-300">
            <b>Training Hunt from a final report.</b> LENS parses the report into its sections —
            methodology / action plan, MITRE coverage, and the findings — and loads the findings as
            ground truth. <b>No analysis runs yet</b>: upload the datasets afterwards and the normal
            analysis + training proceeds.
          </p>
          <div>
            <Label>Final hunt report (.docx) — required</Label>
            <input
              type="file"
              accept=".docx"
              onChange={(e) => setReportFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-md file:border file:border-slate-700 file:bg-slate-800 file:px-3 file:py-1.5 file:text-sm file:text-slate-200 hover:file:bg-slate-700"
            />
            {reportFile && <p className="mt-1 text-xs text-slate-500">Selected: {reportFile.name}</p>}
          </div>
          <div>
            <Label>Methodology file (.docx / .txt / .md) — optional (overrides the report's)</Label>
            <input
              type="file"
              accept=".docx,.txt,.md,.markdown"
              onChange={(e) => setMethodFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-md file:border file:border-slate-700 file:bg-slate-800 file:px-3 file:py-1.5 file:text-sm file:text-slate-200 hover:file:bg-slate-700"
            />
            {methodFile && <p className="mt-1 text-xs text-slate-500">Selected: {methodFile.name}</p>}
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <Label>Name — optional (defaults to the report's filename)</Label>
              <Input
                value={reportMeta.name}
                onChange={(e) => setReportMeta((m) => ({ ...m, name: e.target.value }))}
                placeholder="e.g. Handala / Void Manticore — Jan 2026"
              />
            </div>
            <div>
              <Label>Report Language</Label>
              <Select
                value={reportMeta.report_language}
                onChange={(e) => setReportMeta((m) => ({ ...m, report_language: e.target.value }))}
              >
                <option value="English">English</option>
                <option value="Spanish">Spanish</option>
              </Select>
            </div>
            <div>
              <Label>EDR</Label>
              <Input
                value={reportMeta.edr}
                onChange={(e) => setReportMeta((m) => ({ ...m, edr: e.target.value }))}
                placeholder="e.g. CrowdStrike Falcon"
              />
            </div>
            <div>
              <Label>SIEM</Label>
              <Input
                value={reportMeta.siem}
                onChange={(e) => setReportMeta((m) => ({ ...m, siem: e.target.value }))}
                placeholder="e.g. IBM QRadar"
              />
            </div>
          </div>
          <Button type="submit" variant="primary" disabled={submitting || !reportFile}>
            {submitting ? <Spinner /> : "Parse report & create training hunt"}
          </Button>
        </form>
      )}

      <div className="p-4">
        {hunts === null ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : hunts.length === 0 ? (
          <EmptyState>No hunts yet. Create one to start analyzing datasets.</EmptyState>
        ) : (
          <>
            {/* Sub-tabs: Live / Historic / Training */}
            <div className="mb-3 flex gap-1 border-b border-slate-800">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setListTab(t.id)}
                  className={`-mb-px border-b-2 px-3 py-1.5 text-sm ${
                    active.id === t.id
                      ? "border-indigo-500 text-indigo-300"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            {active.list.length === 0 ? (
              <p className="text-sm text-slate-600">No {active.id} hunts.</p>
            ) : (
              <ul className="space-y-2">
                {active.list.map((h) => (
                  <li
                    key={h.id}
                    className="group rounded border border-slate-800 bg-slate-950/40 transition-colors hover:border-indigo-700"
                  >
                    <div className="flex items-center justify-between gap-3 px-3 py-2.5">
                      <Link to={`${clientBase}/${tid}/hunts/${h.id}`} className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-slate-200 group-hover:text-indigo-300">
                          {h.name}
                        </p>
                        {h.objective && (
                          <p className="mt-1 line-clamp-2 text-xs text-slate-500">{h.objective}</p>
                        )}
                        <p className="mt-1 text-xs text-slate-600">{fmtDate(h.created_at)}</p>
                      </Link>
                      <div className="flex shrink-0 flex-col items-end gap-1.5">
                        <div className="flex items-center gap-1.5">
                          {h.kind === "training" && (
                            <Badge className="border border-amber-800 bg-amber-950 text-amber-300">training</Badge>
                          )}
                          <Badge className="border border-slate-700 bg-slate-800 text-slate-300">{h.status}</Badge>
                        </div>
                        {h.status === "completed" ? (
                          <button onClick={() => setHuntStatus(h, false)} className="text-[11px] text-slate-400 hover:text-indigo-300">
                            Reopen
                          </button>
                        ) : (
                          <button onClick={() => setHuntStatus(h, true)} className="text-[11px] text-slate-400 hover:text-emerald-300">
                            {h.kind === "training" ? "Complete training →" : "Complete →"}
                          </button>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
