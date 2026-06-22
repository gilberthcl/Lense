import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { CalendarEvent, CreateCalendarInput } from "../../lib/types";
import { useToast } from "../Toast";
import { Badge, Button, Card, EmptyState, Input, Label, PanelHeader, Select, Spinner } from "../ui";

const TYPES = ["pre_hunt", "hunt", "post_hunt", "planning", "review", "other"];
const TYPE_COLOR: Record<string, string> = {
  pre_hunt: "border-blue-800 bg-blue-950 text-blue-300",
  hunt: "border-indigo-800 bg-indigo-950 text-indigo-300",
  post_hunt: "border-purple-800 bg-purple-950 text-purple-300",
  planning: "border-amber-800 bg-amber-950 text-amber-300",
  review: "border-emerald-800 bg-emerald-950 text-emerald-300",
  other: "border-slate-700 bg-slate-800 text-slate-300",
};
const EMPTY: CreateCalendarInput = { title: "", event_type: "hunt", event_date: "", notes: "" };

export default function ClientCalendar({ tid }: { tid: string }) {
  const toast = useToast();
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [form, setForm] = useState<CreateCalendarInput>(EMPTY);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.listCalendar(tid).then(setEvents).catch((e: ApiError) => {
      toast.error(e.message);
      setEvents([]);
    });

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return toast.error("Title is required.");
    setBusy(true);
    try {
      await api.createEvent(tid, form);
      setForm(EMPTY);
      toast.success("Event added.");
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await api.deleteEvent(tid, id);
      setEvents((p) => p?.filter((ev) => ev.id !== id) ?? p);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed.");
    }
  };

  return (
    <Card>
      <PanelHeader title="Calendar" subtitle="Hunt cycle & engagement milestones" />
      <form onSubmit={add} className="grid grid-cols-1 gap-3 border-b border-slate-800 bg-slate-950/40 p-4 sm:grid-cols-4">
        <div className="sm:col-span-2"><Label>Title</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Q2 Lateral Movement Hunt" /></div>
        <div>
          <Label>Type</Label>
          <Select value={form.event_type} onChange={(e) => setForm({ ...form, event_type: e.target.value })}>
            {TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
          </Select>
        </div>
        <div><Label>Date</Label><Input type="date" value={form.event_date ?? ""} onChange={(e) => setForm({ ...form, event_date: e.target.value })} /></div>
        <div className="sm:col-span-3"><Label>Notes</Label><Input value={form.notes ?? ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
        <div className="sm:text-right sm:self-end">
          <Button type="submit" variant="primary" disabled={busy}>{busy ? <Spinner /> : "Add Event"}</Button>
        </div>
      </form>

      <div className="p-2">
        {events === null ? (
          <div className="flex items-center gap-2 p-2 text-sm text-slate-500"><Spinner /> Loading…</div>
        ) : events.length === 0 ? (
          <EmptyState>No calendar events yet.</EmptyState>
        ) : (
          <ul className="divide-y divide-slate-800/70">
            {events.map((ev) => (
              <li key={ev.id} className="flex items-center justify-between gap-3 px-2 py-2.5">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="w-24 shrink-0 font-mono text-xs text-slate-500">{ev.event_date || "—"}</span>
                  <div className="min-w-0">
                    <p className="truncate text-sm text-slate-200">{ev.title}</p>
                    {ev.notes && <p className="truncate text-xs text-slate-500">{ev.notes}</p>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge className={`border ${TYPE_COLOR[ev.event_type] ?? TYPE_COLOR.other}`}>
                    {String(ev.event_type).replace(/_/g, " ")}
                  </Badge>
                  <Button variant="ghost" onClick={() => remove(ev.id)}>Remove</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
