import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { CreateTenantInput, Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import { PageHeader } from "../components/Layout";
import { IconClients, IconPlus } from "../components/icons";
import ClientGrid from "../components/ClientGrid";
import { Button, Card, Input, Label, PanelHeader, Spinner, Textarea } from "../components/ui";

function slugify(s: string): string {
  return s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

export default function ClientsPage() {
  const toast = useToast();
  const [clients, setClients] = useState<Tenant[] | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CreateTenantInput>({ name: "", slug: "", context_notes: "" });
  const [slugTouched, setSlugTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = () =>
    api
      .listTenants()
      .then(setClients)
      .catch((e: ApiError) => {
        toast.error(e.message);
        setClients([]);
      });

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error("Name is required.");
    const slug = (form.slug || slugify(form.name)).trim();
    if (!slug) return toast.error("Slug is required.");
    setSubmitting(true);
    try {
      const created = await api.createTenant({
        name: form.name.trim(),
        slug,
        context_notes: form.context_notes?.trim() || undefined,
      });
      toast.success(`Client "${created.name}" created.`);
      setForm({ name: "", slug: "", context_notes: "" });
      setSlugTouched(false);
      setShowForm(false);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to create client.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <PageHeader
        icon={<IconClients width={22} height={22} />}
        title="Clients"
        description="Clients are global — created once and shared across every LENS module. Each is a fully isolated workspace; knowledge, hunts, datasets, and findings never cross between clients."
        actions={
          <Button variant="primary" onClick={() => setShowForm((s) => !s)}>
            <IconPlus width={16} height={16} /> {showForm ? "Close" : "New Client"}
          </Button>
        }
      />

      {showForm && (
        <Card className="mb-6">
          <PanelHeader title="New Client" subtitle="A globally shared, isolated workspace" />
          <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2">
            <div>
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(e) => {
                  const name = e.target.value;
                  setForm((f) => ({ ...f, name, slug: slugTouched ? f.slug : slugify(name) }));
                }}
                placeholder="Acme Corp"
              />
            </div>
            <div>
              <Label>Slug</Label>
              <Input
                value={form.slug}
                onChange={(e) => {
                  setSlugTouched(true);
                  setForm((f) => ({ ...f, slug: e.target.value }));
                }}
                placeholder="acme-corp"
                className="font-mono"
              />
            </div>
            <div className="sm:col-span-2">
              <Label>Context Notes</Label>
              <Textarea
                rows={3}
                value={form.context_notes ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, context_notes: e.target.value }))}
                placeholder="Environment, sectors, known constraints, approved tooling…"
              />
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" variant="primary" disabled={submitting}>
                {submitting ? <Spinner /> : "Create Client"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      <ClientGrid clients={clients} emptyHint="No clients yet. Create one to get started." />
    </div>
  );
}
