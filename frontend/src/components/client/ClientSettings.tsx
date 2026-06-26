import { useRef, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { Tenant, UpdateTenantInput } from "../../lib/types";
import { useToast } from "../Toast";
import BaseModelSelect from "../BaseModelSelect";
import { Button, Card, Input, Label, PanelHeader, Select, Spinner, Textarea } from "../ui";

const FIELDS: { key: keyof UpdateTenantInput; label: string; type?: string }[] = [
  { key: "name", label: "Name" },
  { key: "sector", label: "Sector" },
  { key: "country", label: "Country" },
  { key: "city", label: "City" },
  { key: "edr_platform", label: "EDR Platform" },
  { key: "siem_platform", label: "SIEM Platform" },
  { key: "xdr_platform", label: "XDR Platform" },
  { key: "internal_domain", label: "Internal Domain" },
  { key: "dpe_name", label: "DPE Name" },
  { key: "dpe_email", label: "DPE Email" },
  { key: "pm_name", label: "PM Name" },
  { key: "pm_email", label: "PM Email" },
  { key: "sla_hours", label: "SLA (hours)", type: "number" },
  { key: "contract_start", label: "Contract Start", type: "date" },
  { key: "contract_end", label: "Contract End", type: "date" },
];

export default function ClientSettings({
  client,
  onUpdated,
}: {
  client: Tenant;
  onUpdated: (t: Tenant) => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<UpdateTenantInput>(() => {
    // Tenant carries `null`s; the update type uses `undefined`. Coerce + drop id/meta.
    const out: Record<string, unknown> = {};
    Object.entries(client).forEach(([k, val]) => {
      out[k] = val === null ? undefined : val;
    });
    return out as UpdateTenantInput;
  });
  const [saving, setSaving] = useState(false);
  const logoRef = useRef<HTMLInputElement>(null);
  const contractRef = useRef<HTMLInputElement>(null);

  const set = (k: keyof UpdateTenantInput, v: unknown) => setForm((p) => ({ ...p, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updateClient(String(client.id), form);
      toast.success("Client settings saved.");
      onUpdated(updated);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const upload = async (kind: "logo" | "contract", file?: File) => {
    if (!file) return;
    try {
      const updated =
        kind === "logo"
          ? await api.uploadLogo(String(client.id), file)
          : await api.uploadContract(String(client.id), file);
      toast.success(`${kind === "logo" ? "Logo" : "Contract"} uploaded.`);
      onUpdated(updated);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Upload failed.");
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <PanelHeader title="Client Settings" subtitle="Profile, technology, and account details" />
        <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-3">
          {FIELDS.map((f) => (
            <div key={f.key as string}>
              <Label>{f.label}</Label>
              <Input
                type={f.type ?? "text"}
                value={(form[f.key] as string | number | undefined) ?? ""}
                onChange={(e) =>
                  set(f.key, f.type === "number" ? Number(e.target.value) : e.target.value)
                }
              />
            </div>
          ))}
          <div>
            <Label>Hunt Maturity</Label>
            <Select value={String(form.hunt_maturity ?? 3)} onChange={(e) => set("hunt_maturity", Number(e.target.value))}>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </Select>
          </div>
          <div className="sm:col-span-3">
            <Label>Context Notes</Label>
            <Textarea rows={3} value={form.context_notes ?? ""} onChange={(e) => set("context_notes", e.target.value)} />
          </div>
          <div className="sm:col-span-3">
            <Button variant="primary" onClick={save} disabled={saving}>
              {saving ? <Spinner /> : "Save Settings"}
            </Button>
          </div>
        </div>
      </Card>

      <Card>
        <PanelHeader title="Assets" subtitle="Logo & contract" />
        <div className="flex flex-wrap items-center gap-6 p-4">
          <div className="flex items-center gap-3">
            {client.logo_path ? (
              <img src={api.logoUrl(String(client.id))} alt="logo" className="h-12 w-12 rounded-lg object-cover ring-1 ring-slate-700" />
            ) : (
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-slate-800 text-xs text-slate-500">No logo</div>
            )}
            <input ref={logoRef} type="file" accept="image/*" className="hidden" onChange={(e) => upload("logo", e.target.files?.[0])} />
            <Button variant="ghost" onClick={() => logoRef.current?.click()}>Upload Logo</Button>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-400">
              {client.contract_path ? "Contract on file" : "No contract"}
            </span>
            <input ref={contractRef} type="file" accept=".pdf,.doc,.docx" className="hidden" onChange={(e) => upload("contract", e.target.files?.[0])} />
            <Button variant="ghost" onClick={() => contractRef.current?.click()}>Upload Contract</Button>
            {client.contract_path && (
              <a href={api.contractUrl(String(client.id))} target="_blank" rel="noreferrer" className="text-sm text-indigo-400 hover:text-indigo-300">
                Download
              </a>
            )}
          </div>
        </div>
      </Card>

      {/* Per-client analyst model (W0b) — also surfaced here in Settings. */}
      <Card>
        <PanelHeader
          title="Analyst model"
          subtitle="The AI model this client's analysis runs on — compliance-gated (Western-origin, local, verified)"
        />
        <div className="p-4">
          <BaseModelSelect tid={String(client.id)} />
        </div>
      </Card>
    </div>
  );
}
