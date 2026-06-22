import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { CreateTenantInput, Tenant } from "../lib/types";
import { useToast } from "../components/Toast";
import {
  Button,
  Card,
  EmptyState,
  fmtDate,
  Input,
  Label,
  PanelHeader,
  Spinner,
  Textarea,
} from "../components/ui";

function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export default function TenantsPage() {
  const toast = useToast();
  const [tenants, setTenants] = useState<Tenant[] | null>(null);
  const [form, setForm] = useState<CreateTenantInput>({
    name: "",
    slug: "",
    context_notes: "",
  });
  const [slugTouched, setSlugTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = () =>
    api
      .listTenants()
      .then(setTenants)
      .catch((e: ApiError) => {
        toast.error(e.message);
        setTenants([]);
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
      toast.success(`Tenant "${created.name}" created.`);
      setForm({ name: "", slug: "", context_notes: "" });
      setSlugTouched(false);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to create tenant.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <div className="mb-4">
          <h1 className="text-xl font-semibold text-slate-100">Tenants</h1>
          <p className="mt-1 text-sm text-slate-500">
            Each tenant is a fully isolated workspace — its knowledge base, hunts,
            datasets, and findings never cross over to another tenant.
          </p>
        </div>

        {tenants === null ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading tenants…
          </div>
        ) : tenants.length === 0 ? (
          <Card>
            <EmptyState>No tenants yet. Create one to get started.</EmptyState>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {tenants.map((t) => (
              <Link key={t.id} to={`/tenants/${t.id}`} className="group">
                <Card className="h-full p-4 transition-colors group-hover:border-indigo-700">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-semibold text-slate-100 group-hover:text-indigo-300">
                      {t.name}
                    </h3>
                    <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
                      {t.slug}
                    </span>
                  </div>
                  {t.context_notes && (
                    <p className="mt-2 line-clamp-3 text-xs text-slate-500">
                      {t.context_notes}
                    </p>
                  )}
                  <p className="mt-3 text-xs text-slate-600">
                    Created {fmtDate(t.created_at)}
                  </p>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>

      <div>
        <Card>
          <PanelHeader title="New Tenant" subtitle="Isolated workspace" />
          <form onSubmit={onSubmit} className="space-y-3 p-4">
            <div>
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(e) => {
                  const name = e.target.value;
                  setForm((f) => ({
                    ...f,
                    name,
                    slug: slugTouched ? f.slug : slugify(name),
                  }));
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
            <div>
              <Label>Context Notes</Label>
              <Textarea
                rows={4}
                value={form.context_notes ?? ""}
                onChange={(e) =>
                  setForm((f) => ({ ...f, context_notes: e.target.value }))
                }
                placeholder="Environment, sectors, known constraints…"
              />
            </div>
            <Button type="submit" variant="primary" disabled={submitting} className="w-full">
              {submitting ? <Spinner /> : "Create Tenant"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
