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

  const liveHunts = (hunts ?? []).filter((h) => h.kind !== "training");
  const trainingHunts = (hunts ?? []).filter((h) => h.kind === "training");

  return (
    <Card>
      <PanelHeader
        title="Hunts"
        subtitle="Hypothesis-driven hunt runs scoped to this client"
        right={
          showForm ? (
            <Button variant="ghost" onClick={() => setShowForm(false)}>Close</Button>
          ) : (
            <div className="flex items-center gap-2">
              <Button onClick={() => openForm("live")}>+ New Hunt</Button>
              <Button variant="ghost" onClick={() => openForm("training")}>+ Training Hunt</Button>
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

      <div className="space-y-4 p-4">
        {hunts === null ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : hunts.length === 0 ? (
          <EmptyState>No hunts yet. Create one to start analyzing datasets.</EmptyState>
        ) : (
          <>
            {renderHuntSection("Live hunts", liveHunts)}
            {trainingHunts.length > 0 && renderHuntSection("Training hunts (historic)", trainingHunts)}
          </>
        )}
      </div>
    </Card>
  );

  function renderHuntSection(title: string, list: Hunt[]) {
    if (list.length === 0) {
      return (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
          <p className="text-sm text-slate-600">None yet.</p>
        </div>
      );
    }
    return (
      <div>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
        <ul className="space-y-2">
          {list.map((h) => (
            <li key={h.id}>
              <Link
                to={`${clientBase}/${tid}/hunts/${h.id}`}
                className="group block rounded border border-slate-800 bg-slate-950/40 px-3 py-2.5 transition-colors hover:border-indigo-700"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-medium text-slate-200 group-hover:text-indigo-300">
                    {h.name}
                  </p>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {h.kind === "training" && (
                      <Badge className="border border-amber-800 bg-amber-950 text-amber-300">training</Badge>
                    )}
                    <Badge className="border border-slate-700 bg-slate-800 text-slate-300">
                      {h.status}
                    </Badge>
                  </div>
                </div>
                {h.objective && (
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500">{h.objective}</p>
                )}
                <p className="mt-1 text-xs text-slate-600">{fmtDate(h.created_at)}</p>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    );
  }
}
