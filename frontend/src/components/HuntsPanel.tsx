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
  Spinner,
  Textarea,
} from "./ui";

export default function HuntsPanel({ tid }: { tid: string }) {
  const toast = useToast();
  const [hunts, setHunts] = useState<Hunt[] | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState<CreateHuntInput>({
    name: "",
    objective: "",
    methodology_text: "",
  });

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
      await api.createHunt(tid, {
        name: form.name.trim(),
        objective: form.objective?.trim() || undefined,
        methodology_text: form.methodology_text?.trim() || undefined,
      });
      toast.success("Hunt created.");
      setForm({ name: "", objective: "", methodology_text: "" });
      setShowForm(false);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to create hunt.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <PanelHeader
        title="Hunts"
        subtitle="Hypothesis-driven hunt runs scoped to this tenant"
        right={
          <Button onClick={() => setShowForm((s) => !s)}>
            {showForm ? "Close" : "+ New Hunt"}
          </Button>
        }
      />

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
              rows={3}
              value={form.objective ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, objective: e.target.value }))
              }
              placeholder="What hypothesis is this hunt testing?"
            />
          </div>
          <div>
            <Label>Methodology Override (optional)</Label>
            <Textarea
              rows={4}
              value={form.methodology_text ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, methodology_text: e.target.value }))
              }
              placeholder="Leave blank to inherit the tenant's methodology doc."
              className="font-mono text-xs"
            />
          </div>
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? <Spinner /> : "Create Hunt"}
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
          <ul className="space-y-2">
            {hunts.map((h) => (
              <li key={h.id}>
                <Link
                  to={`/tenants/${tid}/hunts/${h.id}`}
                  className="group block rounded border border-slate-800 bg-slate-950/40 px-3 py-2.5 transition-colors hover:border-indigo-700"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-sm font-medium text-slate-200 group-hover:text-indigo-300">
                      {h.name}
                    </p>
                    <Badge className="shrink-0 border border-slate-700 bg-slate-800 text-slate-300">
                      {h.status}
                    </Badge>
                  </div>
                  {h.objective && (
                    <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                      {h.objective}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-slate-600">
                    {fmtDate(h.created_at)}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
