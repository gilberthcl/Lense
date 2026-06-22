import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { ApprovedSoftware, CreateApprovedSoftwareInput } from "../../lib/types";
import { useToast } from "../Toast";
import { Badge, Button, Card, EmptyState, Input, Label, PanelHeader, Spinner, Textarea } from "../ui";

const EMPTY: CreateApprovedSoftwareInput = {
  name: "",
  vendor: "",
  category: "",
  notes: "",
  is_approved: true,
};

export default function ClientEnvironment({ tid }: { tid: string }) {
  const toast = useToast();
  const [rows, setRows] = useState<ApprovedSoftware[] | null>(null);
  const [form, setForm] = useState<CreateApprovedSoftwareInput>(EMPTY);
  const [bulk, setBulk] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.listApprovedSoftware(tid).then(setRows).catch((e: ApiError) => {
      toast.error(e.message);
      setRows([]);
    });

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error("Name is required.");
    setBusy(true);
    try {
      await api.createApprovedSoftware(tid, form);
      setForm(EMPTY);
      toast.success("Entry added.");
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed.");
    } finally {
      setBusy(false);
    }
  };

  const addBulk = async () => {
    const names = bulk.split("\n").map((s) => s.trim()).filter(Boolean);
    if (names.length === 0) return;
    setBusy(true);
    try {
      await api.bulkApprovedSoftware(tid, names, true);
      setBulk("");
      toast.success(`${names.length} approved entries added.`);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await api.deleteApprovedSoftware(tid, id);
      setRows((p) => p?.filter((r) => r.id !== id) ?? p);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed.");
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <PanelHeader
          title="Approved Software"
          subtitle="Environment baseline — the analyst uses this to suppress false positives and flag policy violations"
        />
        <form onSubmit={add} className="grid grid-cols-1 gap-3 border-b border-slate-800 bg-slate-950/40 p-4 sm:grid-cols-4">
          <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="AnyDesk" /></div>
          <div><Label>Vendor</Label><Input value={form.vendor ?? ""} onChange={(e) => setForm({ ...form, vendor: e.target.value })} /></div>
          <div><Label>Category</Label><Input value={form.category ?? ""} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Remote access" /></div>
          <div><Label>Notes</Label><Input value={form.notes ?? ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={form.is_approved ?? true} onChange={(e) => setForm({ ...form, is_approved: e.target.checked })} />
            Approved (uncheck to mark as a policy violation)
          </label>
          <div className="sm:col-span-3 sm:text-right">
            <Button type="submit" variant="primary" disabled={busy}>{busy ? <Spinner /> : "Add Entry"}</Button>
          </div>
        </form>

        <div className="p-2">
          {rows === null ? (
            <div className="flex items-center gap-2 p-2 text-sm text-slate-500"><Spinner /> Loading…</div>
          ) : rows.length === 0 ? (
            <EmptyState>No approved-software entries yet. Add your baseline to sharpen finding accuracy.</EmptyState>
          ) : (
            <ul className="divide-y divide-slate-800/70">
              {rows.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-3 px-2 py-2.5">
                  <div className="flex min-w-0 items-center gap-2">
                    <Badge
                      className={
                        r.is_approved
                          ? "border border-emerald-800 bg-emerald-950 text-emerald-300"
                          : "border border-red-800 bg-red-950 text-red-300"
                      }
                    >
                      {r.is_approved ? "Approved" : "Not approved"}
                    </Badge>
                    <span className="truncate text-sm text-slate-200">{r.name}</span>
                    {r.vendor && <span className="text-xs text-slate-500">{r.vendor}</span>}
                    {r.category && (
                      <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-400">{r.category}</span>
                    )}
                  </div>
                  <Button variant="ghost" onClick={() => remove(r.id)}>Remove</Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      <Card>
        <PanelHeader title="Bulk add approved software" subtitle="One name per line" />
        <div className="space-y-3 p-4">
          <Textarea
            rows={4}
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
            placeholder={"Microsoft Teams\nVisual Studio Code\nSlack"}
            className="font-mono text-xs"
          />
          <Button variant="primary" onClick={addBulk} disabled={busy || !bulk.trim()}>
            {busy ? <Spinner /> : "Add as Approved"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
