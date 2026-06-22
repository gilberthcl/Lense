import { useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { CreateTenantInput, Tenant } from "../../lib/types";
import { useToast } from "../Toast";
import { Button, Card, Input, Label, PanelHeader, Select, Spinner, Textarea } from "../ui";

function slugify(s: string): string {
  return s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

const STEPS = ["Identity", "Technology", "Account & SLA", "Review"];

type Form = CreateTenantInput & {
  industriesText?: string;
  servicesText?: string;
};

export default function ClientWizard({
  onCreated,
  onCancel,
}: {
  onCreated: (client: Tenant) => void;
  onCancel: () => void;
}) {
  const toast = useToast();
  const [step, setStep] = useState(0);
  const [slugTouched, setSlugTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [f, setF] = useState<Form>({
    name: "",
    slug: "",
    is_global: false,
    hunt_maturity: 3,
    sla_hours: 72,
  });

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((p) => ({ ...p, [k]: v }));

  const next = () => {
    if (step === 0 && !f.name.trim()) return toast.error("Client name is required.");
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const submit = async () => {
    const slug = (f.slug || slugify(f.name)).trim();
    if (!f.name.trim() || !slug) return toast.error("Name and slug are required.");
    setSubmitting(true);
    const { industriesText, servicesText, ...rest } = f;
    const payload: CreateTenantInput = {
      ...rest,
      slug,
      industries: industriesText
        ? industriesText.split(",").map((x) => x.trim()).filter(Boolean).slice(0, 3)
        : undefined,
      contracted_services: servicesText
        ? servicesText.split(",").map((x) => x.trim()).filter(Boolean)
        : undefined,
    };
    try {
      const created = await api.createTenant(payload);
      if (logoFile) {
        try {
          await api.uploadLogo(String(created.id), logoFile);
        } catch {
          toast.error("Client created, but the logo upload failed — add it from Settings.");
        }
      }
      toast.success(`Client "${created.name}" created.`);
      onCreated(created);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to create client.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="mb-6">
      <PanelHeader
        title="New Client"
        subtitle={`Step ${step + 1} of ${STEPS.length} · ${STEPS[step]}`}
        right={
          <div className="flex gap-1.5">
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 w-6 rounded-full ${
                  i <= step ? "bg-indigo-500" : "bg-slate-700"
                }`}
              />
            ))}
          </div>
        }
      />

      <div className="space-y-3 p-4">
        {step === 0 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <Label>Name *</Label>
              <Input
                value={f.name}
                onChange={(e) => {
                  const name = e.target.value;
                  setF((p) => ({ ...p, name, slug: slugTouched ? p.slug : slugify(name) }));
                }}
                placeholder="Acme Corp"
              />
            </div>
            <div>
              <Label>Slug</Label>
              <Input
                value={f.slug}
                onChange={(e) => {
                  setSlugTouched(true);
                  set("slug", e.target.value);
                }}
                className="font-mono"
                placeholder="acme-corp"
              />
            </div>
            <div>
              <Label>Sector</Label>
              <Input value={f.sector ?? ""} onChange={(e) => set("sector", e.target.value)} placeholder="Financial services" />
            </div>
            <div>
              <Label>Industries (comma-separated, max 3)</Label>
              <Input value={f.industriesText ?? ""} onChange={(e) => set("industriesText", e.target.value)} placeholder="Banking, Insurance" />
            </div>
            <div>
              <Label>Country</Label>
              <Input value={f.country ?? ""} onChange={(e) => set("country", e.target.value)} />
            </div>
            <div>
              <Label>City</Label>
              <Input value={f.city ?? ""} onChange={(e) => set("city", e.target.value)} />
            </div>
            <div>
              <Label>Hunt Maturity (1–5)</Label>
              <Select value={String(f.hunt_maturity ?? 3)} onChange={(e) => set("hunt_maturity", Number(e.target.value))}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </Select>
            </div>
            <label className="flex items-center gap-2 pt-6 text-sm text-slate-300">
              <input type="checkbox" checked={!!f.is_global} onChange={(e) => set("is_global", e.target.checked)} />
              Global client
            </label>
          </div>
        )}

        {step === 1 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <Label>EDR Platform</Label>
              <Input value={f.edr_platform ?? ""} onChange={(e) => set("edr_platform", e.target.value)} placeholder="CrowdStrike Falcon" />
            </div>
            <div>
              <Label>SIEM Platform</Label>
              <Input value={f.siem_platform ?? ""} onChange={(e) => set("siem_platform", e.target.value)} placeholder="IBM QRadar" />
            </div>
            <div>
              <Label>XDR Platform</Label>
              <Input value={f.xdr_platform ?? ""} onChange={(e) => set("xdr_platform", e.target.value)} />
            </div>
            <div>
              <Label>Internal Domain(s)</Label>
              <Input value={f.internal_domain ?? ""} onChange={(e) => set("internal_domain", e.target.value)} placeholder="corp.acme.com" />
            </div>
            <div className="sm:col-span-2">
              <Label>Other Technology</Label>
              <Textarea rows={2} value={f.other_tech ?? ""} onChange={(e) => set("other_tech", e.target.value)} />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <Label>Delivery Program Exec (DPE)</Label>
              <Input value={f.dpe_name ?? ""} onChange={(e) => set("dpe_name", e.target.value)} placeholder="Name" />
            </div>
            <div>
              <Label>DPE Email</Label>
              <Input value={f.dpe_email ?? ""} onChange={(e) => set("dpe_email", e.target.value)} />
            </div>
            <div>
              <Label>Project Manager (PM)</Label>
              <Input value={f.pm_name ?? ""} onChange={(e) => set("pm_name", e.target.value)} placeholder="Name" />
            </div>
            <div>
              <Label>PM Email</Label>
              <Input value={f.pm_email ?? ""} onChange={(e) => set("pm_email", e.target.value)} />
            </div>
            <div>
              <Label>SLA (hours)</Label>
              <Input type="number" min="1" value={f.sla_hours ?? 72} onChange={(e) => set("sla_hours", Number(e.target.value))} className="font-mono" />
            </div>
            <div>
              <Label>Contracted Services (comma-separated)</Label>
              <Input value={f.servicesText ?? ""} onChange={(e) => set("servicesText", e.target.value)} placeholder="Threat Hunting, IR" />
            </div>
            <div>
              <Label>Contract Start</Label>
              <Input type="date" value={f.contract_start ?? ""} onChange={(e) => set("contract_start", e.target.value)} />
            </div>
            <div>
              <Label>Contract End</Label>
              <Input type="date" value={f.contract_end ?? ""} onChange={(e) => set("contract_end", e.target.value)} />
            </div>
            <div className="sm:col-span-2">
              <Label>Context Notes</Label>
              <Textarea rows={2} value={f.context_notes ?? ""} onChange={(e) => set("context_notes", e.target.value)} placeholder="Environment, constraints, approved tooling…" />
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-2 text-sm">
            <p className="text-slate-400">Review before creating:</p>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
              {[
                ["Name", f.name],
                ["Slug", f.slug || slugify(f.name)],
                ["Sector", f.sector],
                ["Location", [f.city, f.country].filter(Boolean).join(", ")],
                ["EDR", f.edr_platform],
                ["SIEM", f.siem_platform],
                ["DPE", f.dpe_name],
                ["PM", f.pm_name],
                ["SLA", f.sla_hours ? `${f.sla_hours}h` : ""],
                ["Maturity", `${f.hunt_maturity}/5`],
              ].map(([k, v]) => (
                <div key={k as string} className="flex justify-between gap-3 border-b border-slate-800/60 py-1">
                  <dt className="text-slate-500">{k}</dt>
                  <dd className="truncate text-slate-200">{(v as string) || "—"}</dd>
                </div>
              ))}
            </dl>
            <div className="pt-2">
              <Label>Client Logo (identifies this client across the platform)</Label>
              <div className="flex items-center gap-3">
                {logoFile ? (
                  <img
                    src={URL.createObjectURL(logoFile)}
                    alt=""
                    className="h-12 w-12 rounded-lg object-cover ring-1 ring-slate-700"
                  />
                ) : (
                  <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-slate-800 text-[10px] text-slate-500">
                    No logo
                  </div>
                )}
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setLogoFile(e.target.files?.[0] ?? null)}
                  className="block text-sm text-slate-400 file:mr-3 file:rounded-md file:border file:border-slate-700 file:bg-slate-800 file:px-3 file:py-1.5 file:text-sm file:text-slate-200 hover:file:bg-slate-700"
                />
              </div>
              <p className="mt-1 text-xs text-slate-600">
                Optional — you can also add or change it later from the client's Settings tab.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-slate-800 p-4">
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <div className="flex gap-2">
          {step > 0 && <Button variant="ghost" onClick={back}>Back</Button>}
          {step < STEPS.length - 1 ? (
            <Button variant="primary" onClick={next}>Next</Button>
          ) : (
            <Button variant="primary" onClick={submit} disabled={submitting}>
              {submitting ? <Spinner /> : "Create Client"}
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
