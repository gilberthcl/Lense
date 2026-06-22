import { useEffect, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { Contact, CreateContactInput } from "../../lib/types";
import { useToast } from "../Toast";
import { Badge, Button, Card, EmptyState, Input, Label, PanelHeader, Spinner } from "../ui";

const EMPTY: CreateContactInput = { name: "", title: "", email: "", phone: "", is_primary: false };

export default function ClientContacts({ tid }: { tid: string }) {
  const toast = useToast();
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [form, setForm] = useState<CreateContactInput>(EMPTY);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.listContacts(tid).then(setContacts).catch((e: ApiError) => {
      toast.error(e.message);
      setContacts([]);
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
      await api.createContact(tid, form);
      setForm(EMPTY);
      toast.success("Contact added.");
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await api.deleteContact(tid, id);
      setContacts((p) => p?.filter((c) => c.id !== id) ?? p);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed.");
    }
  };

  return (
    <Card>
      <PanelHeader title="Contacts" subtitle="Client points of contact" />
      <form onSubmit={add} className="grid grid-cols-1 gap-3 border-b border-slate-800 bg-slate-950/40 p-4 sm:grid-cols-4">
        <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div><Label>Title</Label><Input value={form.title ?? ""} onChange={(e) => setForm({ ...form, title: e.target.value })} /></div>
        <div><Label>Email</Label><Input value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
        <div><Label>Phone</Label><Input value={form.phone ?? ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={!!form.is_primary} onChange={(e) => setForm({ ...form, is_primary: e.target.checked })} />
          Primary contact
        </label>
        <div className="sm:col-span-3 sm:text-right">
          <Button type="submit" variant="primary" disabled={busy}>{busy ? <Spinner /> : "Add Contact"}</Button>
        </div>
      </form>

      <div className="p-2">
        {contacts === null ? (
          <div className="flex items-center gap-2 p-2 text-sm text-slate-500"><Spinner /> Loading…</div>
        ) : contacts.length === 0 ? (
          <EmptyState>No contacts yet.</EmptyState>
        ) : (
          <ul className="divide-y divide-slate-800/70">
            {contacts.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 px-2 py-2.5">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-sm text-slate-200">
                    {c.name}
                    {c.is_primary && <Badge className="border border-emerald-800 bg-emerald-950 text-emerald-300">Primary</Badge>}
                  </p>
                  <p className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-slate-500">
                    {c.title && <span>{c.title}</span>}
                    {c.email && <span>{c.email}</span>}
                    {c.phone && <span>{c.phone}</span>}
                  </p>
                </div>
                <Button variant="ghost" onClick={() => remove(c.id)}>Remove</Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
